"""Graphics driver settings (global, for all games) through each vendor's own driver API:

- NVIDIA: NVAPI driver settings (DRS), nvapi64.dll. IDs from NVIDIA's NvApiDriverSettings.h / nvapi_interface.h
  (github.com/NVIDIA/nvapi). Same store the NVIDIA Control Panel uses.
- AMD: ADLX 3D settings, amdadlx64.dll (vtable order from the ADLX SDK headers, github.com/GPUOpen-LibrariesAndSDKs/ADLX).
  Same settings as AMD Software.
- Intel: Intel Graphics Control Library, ControlLib.dll (igcl_api.h, github.com/intel/drivers.gpu.control-library).

All three DLLs ship with the graphics driver; nothing is bundled. Every call checks the vendor's result code."""
import ctypes
from ctypes import POINTER, byref, c_int32, c_uint8, c_uint32, c_uint64, c_void_p

FPS = "fps"  # option list marker: 0 = off, otherwise a frame rate cap

# ---------------- NVIDIA ----------------
NV_FN = {"init": 0x0150E828, "create": 0x0694D52E, "destroy": 0xDAD9CFF8, "load": 0x375DBD6B, "save": 0xFCBC7E14,
         "base": 0xDA8466A0, "get": 0x73BF8338, "set": 0x577DD202, "delete": 0xE4A26362}
P, H = c_void_p, c_void_p  # pointer, handle
NV_ARGS = {"init": [], "create": [P], "destroy": [H], "load": [H], "save": [H], "base": [H, P],
           "get": [H, H, c_uint32, P], "set": [H, H, P], "delete": [H, H, c_uint32]}
NV_SETTINGS = [  # key, title, setting id, [(label, value)], default
    ("power", "Power management mode", 0x1057EB71,
     [("Optimal power", 5), ("Normal (adaptive)", 0), ("Prefer maximum performance", 1)], 5),
    ("latency", "Low latency mode", 0x007BA09E, [("Off", 0), ("On", 1)], 0),
    ("vsync", "Vertical sync", 0x00A879CF,
     [("Use the 3D application setting", 0x60925292), ("Off", 0x08416747), ("On", 0x47814940)], 0x60925292),
    ("texture", "Texture filtering - quality", 0x00CE2691,
     [("High quality", 0xFFFFFFF6), ("Quality", 0), ("Performance", 10), ("High performance", 20)], 0),
    ("threaded", "Threaded optimization (OpenGL)", 0x20C1221E, [("Auto", 0), ("On", 1), ("Off", 2)], 0),
    ("fps", "Max frame rate", 0x10835002, FPS, 0),
]

class NvSetting(ctypes.Structure):  # NVDRS_SETTING_V1, #pragma pack(4): 12320 bytes
    _pack_ = 4
    _fields_ = [("version", c_uint32), ("name", ctypes.c_uint16 * 2048), ("id", c_uint32), ("type", c_uint32),
                ("location", c_uint32), ("is_current_predefined", c_uint32), ("is_predefined_valid", c_uint32),
                ("predefined", c_uint8 * 4100), ("current", c_uint8 * 4100)]

class Nvidia:
    name = "NVIDIA"
    def __init__(self):
        dll = ctypes.CDLL("nvapi64.dll")
        dll.nvapi_QueryInterface.restype, dll.nvapi_QueryInterface.argtypes = c_void_p, [c_uint32]
        self._q = dll.nvapi_QueryInterface
        self._call("init")

    def _call(self, fn, *args):
        ptr = self._q(NV_FN[fn])
        if not ptr:
            raise RuntimeError(f"NVAPI: {fn} not available")
        r = ctypes.CFUNCTYPE(c_int32, *NV_ARGS[fn])(ptr)(*args)
        if r and not (fn == "get" and r == -160):  # -160 = NVAPI_SETTING_NOT_FOUND: driver default is used
            raise RuntimeError(f"NVAPI {fn} error {r}")
        return r

    def _session(self, work, save=False):
        h, prof = c_void_p(), c_void_p()
        self._call("create", ctypes.addressof(h))
        try:
            self._call("load", h)
            self._call("base", h, ctypes.addressof(prof))
            out = work(h, prof)
            if save:
                self._call("save", h)
            return out
        finally:
            self._call("destroy", h)

    def settings(self):
        def read(h, prof):
            out = []
            for key, title, sid, opts, default in NV_SETTINGS:
                s = NvSetting(version=ctypes.sizeof(NvSetting) | 1 << 16)
                found = self._call("get", h, prof, sid, ctypes.addressof(s)) == 0
                value = int.from_bytes(bytes(s.current[:4]), "little") if found else default
                out.append({"key": key, "title": title, "options": opts, "value": value})
            return out
        return self._session(read)

    def set(self, key, value):
        _, _, sid, _, default = next(x for x in NV_SETTINGS if x[0] == key)
        def write(h, prof):
            if value == default:
                try:
                    self._call("delete", h, prof, sid)  # back to the driver's own default
                except RuntimeError:
                    pass
                return
            s = NvSetting(version=ctypes.sizeof(NvSetting) | 1 << 16, id=sid, type=0)  # 0 = NVDRS_DWORD_TYPE
            s.current[:4] = list(int(value).to_bytes(4, "little"))
            self._call("set", h, prof, ctypes.addressof(s))
        self._session(write, save=True)

# ---------------- AMD ----------------
def _vcall(obj, index, *args, res=c_int32):
    """Call method `index` of an ADLX interface (C vtable as in the ADLX headers). Arguments are ctypes values
    (c_uint8 / c_int32 / c_uint32 / c_void_p) or out-parameters given as ctypes.byref(...)."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    types = [c_void_p if not isinstance(a, ctypes._SimpleCData) else type(a) for a in args]
    fn = ctypes.CFUNCTYPE(res, c_void_p, *types)(vtbl[index])
    return fn(obj, *[ctypes.cast(a, c_void_p) if type(a).__name__ == "CArgObject" else a for a in args])

# key, title, index in IADLX3DSettingsServices, IsEnabled, SetEnabled, extra
AMD_SETTINGS = [("antilag", "Radeon Anti-Lag", 3, 4, 5), ("chill", "Radeon Chill", 4, 4, 8),
                ("boost", "Radeon Boost", 5, 4, 7), ("sharpening", "Radeon Image Sharpening", 6, 4, 7),
                ("esync", "Enhanced Sync", 7, 4, 5)]
AMD_VSYNC = [("Always off", 0), ("Off, unless application specifies", 1), ("On, unless application specifies", 2),
             ("Always on", 3)]

class Amd:
    name = "AMD"
    def __init__(self):
        self.dll = ctypes.CDLL("amdadlx64.dll")
        ver, self.sys = c_uint64(), c_void_p()
        if self.dll.ADLXQueryFullVersion(byref(ver)) or self.dll.ADLXInitialize(ver, byref(self.sys)):
            raise RuntimeError("ADLX could not start (AMD driver too old?)")
        gpus, self.gpu, self.svc = c_void_p(), c_void_p(), c_void_p()
        self._ok(_vcall(self.sys, 1, byref(gpus)))                    # IADLXSystem::GetGPUs
        if not _vcall(gpus, 3, res=c_uint32):                         # IADLXGPUList::Size
            raise RuntimeError("No AMD graphics card")
        self._ok(_vcall(gpus, 11, c_uint32(0), byref(self.gpu)))      # IADLXGPUList::At_GPUList
        self._ok(_vcall(self.sys, 7, byref(self.svc)))                # IADLXSystem::Get3DSettingsServices

    @staticmethod
    def _ok(r):
        if r not in (0, 1, 2):  # ADLX_OK, ADLX_ALREADY_ENABLED, ADLX_ALREADY_INITIALIZED
            raise RuntimeError(f"ADLX error {r}")

    def _iface(self, index):
        out = c_void_p()
        self._ok(_vcall(self.svc, index, self.gpu, byref(out)))
        return out

    def _bool(self, obj, index):
        v = c_uint8()
        self._ok(_vcall(obj, index, byref(v)))
        return bool(v.value)

    def settings(self):
        out = []
        for key, title, idx, is_en, _ in AMD_SETTINGS:
            f = self._iface(idx)
            if self._bool(f, 3):  # IsSupported
                out.append({"key": key, "title": title, "options": [("Off", 0), ("On", 1)],
                            "value": int(self._bool(f, is_en))})
            _vcall(f, 1)  # Release
        f = self._iface(8)  # Wait for vertical refresh
        if self._bool(f, 3):
            mode = c_int32()
            self._ok(_vcall(f, 5, byref(mode)))
            out.append({"key": "vsync", "title": "Wait for vertical refresh", "options": AMD_VSYNC, "value": mode.value})
        _vcall(f, 1)
        f = self._iface(9)  # Frame rate target control
        if self._bool(f, 3):
            fps = c_int32()
            self._ok(_vcall(f, 6, byref(fps)))
            out.append({"key": "fps", "title": "Frame rate target control", "options": FPS,
                        "value": fps.value if self._bool(f, 4) else 0})
        _vcall(f, 1)
        return out

    def set(self, key, value):
        if key == "vsync":
            f = self._iface(8)
            self._ok(_vcall(f, 6, c_int32(value)))
        elif key == "fps":
            f = self._iface(9)
            if value:
                self._ok(_vcall(f, 8, c_int32(value)))
            self._ok(_vcall(f, 7, c_uint8(1 if value else 0)))
        else:
            _, _, idx, _, set_en = next(x for x in AMD_SETTINGS if x[0] == key)
            f = self._iface(idx)
            self._ok(_vcall(f, set_en, c_uint8(1 if value else 0)))
        _vcall(f, 1)

# ---------------- Intel ----------------
class CtlInitArgs(ctypes.Structure):
    _fields_ = [("Size", c_uint32), ("Version", c_uint8), ("AppVersion", c_uint32), ("flags", c_uint32),
                ("SupportedVersion", c_uint32), ("uid", c_uint8 * 16)]

class CtlValue(ctypes.Structure):  # ctl_property_t union (8 bytes): IntType {bool Enable; int32 Value} / EnumType
    _fields_ = [("a", c_uint32), ("b", c_int32)]

class Ctl3D(ctypes.Structure):  # ctl_3d_feature_getset_t
    _fields_ = [("Size", c_uint32), ("Version", c_uint8), ("FeatureType", c_int32), ("ApplicationName", ctypes.c_char_p),
                ("ApplicationNameLength", ctypes.c_int8), ("bSet", c_uint8), ("ValueType", c_int32),
                ("Value", CtlValue), ("CustomValueSize", c_int32), ("pCustomValue", c_void_p)]

INTEL_FLIP = [("Application default", 1), ("Off", 2), ("On", 4), ("Smooth sync", 8), ("Speed sync", 16)]

class Intel:
    name = "Intel"
    def __init__(self):
        self.dll = ctypes.CDLL("ControlLib.dll")
        args, self.h = CtlInitArgs(Size=ctypes.sizeof(CtlInitArgs), AppVersion=1 << 16 | 1), c_void_p()
        self._ok(self.dll.ctlInit(byref(args), byref(self.h)))
        n = c_uint32(0)
        self._ok(self.dll.ctlEnumerateDevices(self.h, byref(n), None))
        if not n.value:
            raise RuntimeError("No Intel graphics")
        devs = (c_void_p * n.value)()
        self._ok(self.dll.ctlEnumerateDevices(self.h, byref(n), devs))
        self.dev = c_void_p(devs[0])

    @staticmethod
    def _ok(r):
        if r:
            raise RuntimeError(f"Intel graphics control error 0x{r & 0xffffffff:08x}")

    def _feature(self, ftype, vtype, value=None):
        f = Ctl3D(Size=ctypes.sizeof(Ctl3D), FeatureType=ftype, ApplicationName=b"", ValueType=vtype)  # "" = global
        if value is not None:
            f.bSet, f.Value = 1, value
        self._ok(self.dll.ctlGetSet3DFeature(self.dev, byref(f)))
        return f.Value

    def settings(self):
        out = []
        try:  # 9 = CTL_3D_FEATURE_GAMING_FLIP_MODES, 4 = enum value
            out.append({"key": "vsync", "title": "Vertical sync", "options": INTEL_FLIP,
                        "value": self._feature(9, 4).a})
        except RuntimeError:
            pass
        try:  # 2 = CTL_3D_FEATURE_FRAME_LIMIT, 2 = int32 value {Enable, Value}
            v = self._feature(2, 2)
            out.append({"key": "fps", "title": "Frame rate limiter", "options": FPS, "value": v.b if v.a & 0xff else 0})
        except RuntimeError:
            pass
        return out

    def set(self, key, value):
        if key == "vsync":
            self._feature(9, 4, CtlValue(a=value))
        else:
            self._feature(2, 2, CtlValue(a=1 if value else 0, b=value))

VENDORS = {"NVIDIA": Nvidia, "AMD": Amd, "Intel": Intel}

class NoDriver(RuntimeError):
    pass
_open = {}

def open_vendor(vendor):
    """Driver API object for 'NVIDIA', 'AMD' or 'Intel' (started once); raises when the driver lacks it."""
    if vendor not in _open:
        try:
            _open[vendor] = VENDORS[vendor]()
        except OSError as e:  # the driver's DLL is missing (driver not installed, too old, or Microsoft basic driver)
            raise NoDriver(str(e)) from e
    return _open[vendor]
