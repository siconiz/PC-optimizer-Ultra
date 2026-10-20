"""Drive health (Windows Storage WMI: health status, SMART-based reliability counters) and a quick speed test."""
import ctypes, os, random, time
from ctypes import wintypes
from .storage import drive_kind

# Typical sequential read range in MB/s for a healthy drive of each kind (see README for sources).
TYPICAL = {"HDD": (80, 270), "SSD": (400, 600), "NVMe SSD": (1500, 14000), "USB": (20, 1000)}
# A common drive of each kind for the comparison bar: 7200 rpm HDD ~180 MB/s, SATA SSD ~550 (SATA 6 Gb/s limit),
# PCIe 3.0 NVMe ~3,500, USB 3 flash drive ~200 (box speeds; see README for sources)
AVERAGE = {"HDD": 180, "SSD": 550, "NVMe SSD": 3500, "USB": 200}
HEALTH = {0: "Healthy", 1: "Warning", 2: "Unhealthy"}
MEDIA = {3: "HDD", 4: "SSD", 5: "SCM"}
BUS = {7: "USB", 11: "SATA", 17: "NVMe", 8: "RAID", 10: "SAS"}

def health():
    import wmi
    c = wmi.WMI(namespace=r"root\Microsoft\Windows\Storage")
    rel = {}
    try:
        rel = {r.DeviceId: r for r in c.MSFT_StorageReliabilityCounter()}
    except Exception:
        pass
    out = []
    for d in c.MSFT_PhysicalDisk():
        r = rel.get(d.DeviceId)
        out.append({"name": d.FriendlyName, "media": MEDIA.get(d.MediaType, "-"), "bus": BUS.get(d.BusType, "-"),
                    "size_gb": round(int(d.Size or 0) / 1e9), "health": HEALTH.get(d.HealthStatus, "Unknown"),
                    "temp": getattr(r, "Temperature", None) or None, "wear": getattr(r, "Wear", None),
                    "hours": getattr(r, "PowerOnHours", None) or None,
                    "errors": (getattr(r, "ReadErrorsUncorrected", 0) or 0) + (getattr(r, "WriteErrorsUncorrected", 0) or 0)})
    return out

def drives():
    import psutil
    return [p.device[:2] for p in psutil.disk_partitions() if p.fstype and "cdrom" not in p.opts]

def _io(h, buf, size, write):
    n = wintypes.DWORD()
    f = ctypes.windll.kernel32.WriteFile if write else ctypes.windll.kernel32.ReadFile
    if not f(wintypes.HANDLE(h), ctypes.c_void_p(buf), size, ctypes.byref(n), None):
        raise ctypes.WinError()
    return n.value

def _seek(h, pos):
    ctypes.windll.kernel32.SetFilePointerEx(wintypes.HANDLE(h), ctypes.c_longlong(pos), None, 0)

def bench(drive, size_mb=512, seconds=3):
    """Sequential write/read (8 MiB blocks) and random 4 KiB reads, bypassing the Windows cache.
    Returns MB/s for seq_write / seq_read and IOPS + MB/s for random reads."""
    k32 = ctypes.windll.kernel32
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.VirtualAlloc.restype = ctypes.c_void_p
    path = os.path.join(drive + "\\", "PCOptimizer-speedtest.tmp")
    block = 8 << 20  # 8 MiB transfers: the drive splits them internally, so NVMe gets close to its rated speed
    buf = k32.VirtualAlloc(None, block, 0x3000, 0x04)  # page aligned, as unbuffered I/O requires
    ctypes.memmove(buf, os.urandom(block), block)  # random data so compressing drives cannot cheat
    # GENERIC_READ|WRITE, CREATE_ALWAYS, NO_BUFFERING | WRITE_THROUGH | DELETE_ON_CLOSE
    h = k32.CreateFileW(path, 0xC0000000, 0, None, 2, 0x20000000 | 0x80000000 | 0x04000000, None)
    if h in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError()
    try:
        t0 = time.perf_counter()
        for _ in range(size_mb // 8):
            _io(h, buf, block, True)
        write = size_mb / (time.perf_counter() - t0)
        _seek(h, 0)
        t0 = time.perf_counter()
        for _ in range(size_mb // 8):
            _io(h, buf, block, False)
        read = size_mb / (time.perf_counter() - t0)
        n, t0 = 0, time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            _seek(h, random.randrange(size_mb * 256) * 4096)
            _io(h, buf, 4096, False)
            n += 1
        iops = n / (time.perf_counter() - t0)
    finally:
        k32.CloseHandle(wintypes.HANDLE(h))
        k32.VirtualFree(ctypes.c_void_p(buf), 0, 0x8000)
    kind = drive_kind(drive)
    lo, hi = TYPICAL.get(kind, (0, 0))
    avg = AVERAGE.get(kind)
    return {"kind": kind, "seq_write": round(write), "seq_read": round(read), "rand_iops": round(iops), "average": avg,
            "vs_avg": round(read * 100 / avg) if avg else None,
            "rand_mb": round(iops * 4096 / 2**20, 1), "typical": (lo, hi),
            "verdict": "Unknown" if not lo else "Slow" if read < lo * 0.7 else "Normal"}
