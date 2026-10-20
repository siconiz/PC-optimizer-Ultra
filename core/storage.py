"""Drive type (NVMe SSD / SSD / HDD / USB) via IOCTL_STORAGE_QUERY_PROPERTY."""
import ctypes, struct
from ctypes import wintypes

IOCTL_STORAGE_QUERY_PROPERTY = 0x2D1400
IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x560000
DEVICE_PROPERTY, SEEK_PENALTY_PROPERTY = 0, 7
BUS_USB, BUS_NVME = 7, 17

def _open(path):
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = wintypes.HANDLE
    h = k32.CreateFileW(path, 0, 0x1 | 0x2, None, 3, 0, None)  # no access rights needed for queries
    return None if h in (None, wintypes.HANDLE(-1).value) else h

def _ioctl(h, code, inbuf, outsize):
    out = ctypes.create_string_buffer(outsize)
    n = wintypes.DWORD()
    ok = ctypes.windll.kernel32.DeviceIoControl(wintypes.HANDLE(h), code, inbuf, len(inbuf) if inbuf else 0,
                                                out, outsize, ctypes.byref(n), None)
    return out.raw[:n.value] if ok else None

def _query(h, prop, outsize):
    return _ioctl(h, IOCTL_STORAGE_QUERY_PROPERTY, struct.pack("<II4x", prop, 0), outsize)

def _props(h):
    sp = _query(h, SEEK_PENALTY_PROPERTY, 12)  # DEVICE_SEEK_PENALTY_DESCRIPTOR
    dd = _query(h, DEVICE_PROPERTY, 1024)      # STORAGE_DEVICE_DESCRIPTOR, BusType at offset 28
    seek = bool(sp[8]) if sp and len(sp) >= 9 else None
    bus = struct.unpack_from("<I", dd, 28)[0] if dd and len(dd) >= 32 else None
    return seek, bus

def _with(path, fn):
    h = _open(path)
    if not h:
        return None
    try:
        return fn(h)
    finally:
        ctypes.windll.kernel32.CloseHandle(wintypes.HANDLE(h))

def drive_kind(drive):
    """drive: 'C:'. Returns 'NVMe SSD', 'SSD', 'HDD', 'USB' or 'Unknown'."""
    seek, bus = _with(f"\\\\.\\{drive}", _props) or (None, None)
    if seek is None and bus is None:  # fall back to the physical disk behind the volume
        ext = _with(f"\\\\.\\{drive}", lambda h: _ioctl(h, IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, None, 64))
        if ext and len(ext) >= 12:
            disk = struct.unpack_from("<I", ext, 8)[0]
            seek, bus = _with(f"\\\\.\\PhysicalDrive{disk}", _props) or (None, None)
    if bus == BUS_USB:
        return "USB"
    if seek is False:
        return "NVMe SSD" if bus == BUS_NVME else "SSD"
    if seek is True:
        return "HDD"
    return "Unknown"
