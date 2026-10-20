"""GPU info for any vendor (NVIDIA, AMD, Intel; integrated and discrete).
DXGI lists adapters, PDH counters give usage, D3DKMT gives temperature and fan speed when the driver reports them."""
import ctypes, re
from ctypes import wintypes
import win32pdh

VENDORS = {0x10DE: "NVIDIA", 0x1002: "AMD", 0x8086: "Intel"}
LUID_RE = re.compile(r"luid_0x[0-9a-f]+_0x[0-9a-f]+", re.I)

class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]

class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [("Description", ctypes.c_wchar * 128), ("VendorId", ctypes.c_uint), ("DeviceId", ctypes.c_uint),
                ("SubSysId", ctypes.c_uint), ("Revision", ctypes.c_uint), ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t), ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", LUID), ("Flags", ctypes.c_uint)]

class OPENADAPTERFROMLUID(ctypes.Structure):
    _fields_ = [("AdapterLuid", LUID), ("hAdapter", ctypes.c_uint)]

class QUERYADAPTERINFO(ctypes.Structure):
    _fields_ = [("hAdapter", ctypes.c_uint), ("Type", ctypes.c_int), ("pPrivateDriverData", ctypes.c_void_p),
                ("PrivateDriverDataSize", ctypes.c_uint)]

class ADAPTER_PERFDATA(ctypes.Structure):
    _fields_ = [("PhysicalAdapterIndex", ctypes.c_uint32), ("MemoryFrequency", ctypes.c_uint64),
                ("MaxMemoryFrequency", ctypes.c_uint64), ("MaxMemoryFrequencyOC", ctypes.c_uint64),
                ("MemoryBandwidth", ctypes.c_uint64), ("PCIEBandwidth", ctypes.c_uint64), ("FanRPM", ctypes.c_ulong),
                ("Power", ctypes.c_ulong), ("Temperature", ctypes.c_ulong), ("PowerStateOverride", ctypes.c_ubyte)]

IID_FACTORY1 = GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))
KMTQAITYPE_ADAPTERPERFDATA = 61

def _method(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])

_cache = []

def adapters():
    if _cache:
        return _cache[0]
    out, factory = [], ctypes.c_void_p()
    if ctypes.windll.dxgi.CreateDXGIFactory1(ctypes.byref(IID_FACTORY1), ctypes.byref(factory)) == 0:
        try:
            i = 0
            while True:
                ad = ctypes.c_void_p()
                if _method(factory, 12, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))(factory, i, ctypes.byref(ad)):
                    break  # EnumAdapters1 -> DXGI_ERROR_NOT_FOUND
                d = DXGI_ADAPTER_DESC1()
                _method(ad, 10, ctypes.POINTER(DXGI_ADAPTER_DESC1))(ad, ctypes.byref(d))  # GetDesc1
                _method(ad, 2)(ad)  # Release
                if not d.Flags & 2:  # skip software adapters
                    l = d.AdapterLuid
                    out.append({"name": d.Description, "vendor": VENDORS.get(d.VendorId, "Other"),
                                "vram_gb": round(d.DedicatedVideoMemory / 2**30, 1), "low": l.LowPart, "high": l.HighPart,
                                "luid": f"luid_0x{l.HighPart & 0xFFFFFFFF:08x}_0x{l.LowPart:08x}"})
                i += 1
        finally:
            _method(factory, 2)(factory)
    _cache.append(out)
    return out

def thermal(a):
    """Temperature (C) and fan RPM reported by the driver, or None. Usually only discrete GPUs report them."""
    gdi = ctypes.windll.gdi32
    o = OPENADAPTERFROMLUID(LUID(a["low"], a["high"]), 0)
    if gdi.D3DKMTOpenAdapterFromLuid(ctypes.byref(o)):
        return None, None
    try:
        pd = ADAPTER_PERFDATA()
        q = QUERYADAPTERINFO(o.hAdapter, KMTQAITYPE_ADAPTERPERFDATA, ctypes.cast(ctypes.pointer(pd), ctypes.c_void_p),
                             ctypes.sizeof(pd))
        if gdi.D3DKMTQueryAdapterInfo(ctypes.byref(q)):
            return None, None
        return (pd.Temperature / 10 if pd.Temperature else None), (pd.FanRPM or None)
    finally:
        gdi.D3DKMTCloseAdapter(ctypes.byref(ctypes.c_uint(o.hAdapter)))

class Usage:
    """GPU usage (busiest engine, like Task Manager) and dedicated memory in use, per adapter LUID."""
    def __init__(self):
        self.q = win32pdh.OpenQuery()
        self.util = win32pdh.AddEnglishCounter(self.q, r"\GPU Engine(*)\Utilization Percentage")
        self.mem = win32pdh.AddEnglishCounter(self.q, r"\GPU Adapter Memory(*)\Dedicated Usage")
        win32pdh.CollectQueryData(self.q)

    def read(self):
        win32pdh.CollectQueryData(self.q)
        engines, util, mem = {}, {}, {}
        for inst, v in win32pdh.GetFormattedCounterArray(self.util, win32pdh.PDH_FMT_DOUBLE).items():
            m, e = LUID_RE.search(inst), re.search(r"engtype_(\w+)", inst)
            if m and e:
                key = (m.group(0).lower(), e.group(1))
                engines[key] = engines.get(key, 0) + v
        for (luid, _), v in engines.items():
            util[luid] = min(100.0, max(util.get(luid, 0), v))
        for inst, v in win32pdh.GetFormattedCounterArray(self.mem, win32pdh.PDH_FMT_LARGE).items():
            if m := LUID_RE.search(inst):
                mem[m.group(0).lower()] = mem.get(m.group(0).lower(), 0) + v
        return util, mem

def snapshot(usage=None):
    util, mem = usage.read() if usage else ({}, {})
    out = []
    try:
        ads = adapters()
    except Exception:
        ads = []
    for a in ads:
        try:
            temp, fan = thermal(a)
        except Exception:
            temp, fan = None, None
        out.append({**a, "util": util.get(a["luid"]), "vram_used_gb": round(mem[a["luid"]] / 2**30, 1)
                    if a["luid"] in mem else None, "temp": temp, "fan": fan})
    return out
