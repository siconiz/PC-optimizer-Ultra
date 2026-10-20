"""Memory: usage breakdown, top processes, page file, standby purge and Windows Memory Diagnostic."""
import ctypes, subprocess
import psutil
import win32pdh
from .i18n import t

COUNTERS = {"commit": r"\Memory\Committed Bytes", "limit": r"\Memory\Commit Limit",
            "sb_n": r"\Memory\Standby Cache Normal Priority Bytes", "sb_r": r"\Memory\Standby Cache Reserve Bytes",
            "sb_c": r"\Memory\Standby Cache Core Bytes", "modified": r"\Memory\Modified Page List Bytes",
            "free": r"\Memory\Free & Zero Page List Bytes"}
PROTECTED = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
             "winlogon.exe", "svchost.exe", "dwm.exe", "explorer.exe", "memcompression", "memory compression",
             "fontdrvhost.exe", "system idle process", "pcoptimizer.exe", "python.exe", "pythonw.exe"}
_query = []

def _gb(x):
    return round(x / 2**30, 1) if x else None

def stats():
    if not _query:
        q, h = win32pdh.OpenQuery(), {}
        for k, p in COUNTERS.items():
            try:
                h[k] = win32pdh.AddEnglishCounter(q, p)
            except Exception:
                pass
        _query.append((q, h))
    q, h = _query[0]
    win32pdh.CollectQueryData(q)
    v = {}
    for k, hc in h.items():
        try:
            v[k] = win32pdh.GetFormattedCounterValue(hc, win32pdh.PDH_FMT_LARGE)[1]
        except Exception:
            pass
    vm = psutil.virtual_memory()
    return {"total": _gb(vm.total), "used": _gb(vm.total - vm.available), "available": _gb(vm.available),
            "percent": vm.percent, "commit": _gb(v.get("commit")), "limit": _gb(v.get("limit")),
            "standby": _gb(sum(v.get(k, 0) for k in ("sb_n", "sb_r", "sb_c"))),
            "modified": _gb(v.get("modified")), "free": _gb(v.get("free"))}

def top_apps(n=15):
    """Memory per app name (all its processes together), largest first."""
    apps = {}
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        mi, name = p.info["memory_info"], p.info["name"] or "?"
        if mi:
            a = apps.setdefault(name, {"name": name, "mb": 0, "pids": []})
            a["mb"] += mi.rss / 2**20
            a["pids"].append(p.info["pid"])
    out = sorted(apps.values(), key=lambda a: -a["mb"])[:n]
    for a in out:
        a["mb"] = round(a["mb"])
        a["protected"] = a["name"].lower() in PROTECTED
    return out

def end_app(app):
    if app["protected"]:
        raise RuntimeError(t("{name} is part of Windows and cannot be ended here.", name=app["name"]))
    done = 0
    for pid in app["pids"]:
        try:
            psutil.Process(pid).terminate()
            done += 1
        except (psutil.Error, OSError):
            pass
    return done

def pagefile():
    import wmi
    c = wmi.WMI()
    auto = bool(c.Win32_ComputerSystem()[0].AutomaticManagedPagefile)
    files = [{"path": f.Name, "size_mb": f.AllocatedBaseSize, "used_mb": f.CurrentUsage, "peak_mb": f.PeakUsage}
             for f in c.Win32_PageFileUsage()]
    return auto, files

def purge_standby():
    """Same as RAMMap 'Empty Standby List'. Returns standby GB before the purge."""
    import win32api, win32security
    tok = win32security.OpenProcessToken(win32api.GetCurrentProcess(),
                                         win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY)
    luid = win32security.LookupPrivilegeValue(None, "SeProfileSingleProcessPrivilege")
    win32security.AdjustTokenPrivileges(tok, False, [(luid, win32security.SE_PRIVILEGE_ENABLED)])
    before = stats()["standby"]
    cmd = ctypes.c_int(4)  # MemoryPurgeStandbyList
    status = ctypes.windll.ntdll.NtSetSystemInformation(80, ctypes.byref(cmd), ctypes.sizeof(cmd))  # SystemMemoryListInformation
    if status:
        raise RuntimeError(t("Windows refused the request (status 0x{s:08X}).", s=status & 0xFFFFFFFF))
    return before

def open_memory_diagnostic():
    subprocess.Popen(["mdsched.exe"])

def open_virtual_memory_settings():
    subprocess.Popen(["SystemPropertiesPerformance.exe"])

class _PerfInfo(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_ulong)] + [(n, ctypes.c_size_t) for n in (
        "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable", "SystemCache",
        "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + [(n, ctypes.c_ulong) for n in (
        "HandleCount", "ProcessCount", "ThreadCount")]

def recommend_pagefile():
    """Sizes from Microsoft's rules for a system-managed page file (Windows 10/11): minimum RAM/8 (max 32 GB) or
    enough to cover the peak commit charge, maximum 3 x RAM or 4 GB (whichever is larger), at most volume / 8."""
    pi = _PerfInfo(ctypes.sizeof(_PerfInfo))
    ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), pi.cb)
    gb = pi.PageSize / 2**30
    ram, peak = pi.PhysicalTotal * gb, pi.CommitPeak * gb
    vol = psutil.disk_usage("C:\\").total / 2**30
    initial = max(min(ram / 8, 32), peak * 1.25 - ram, 1)
    maximum = max(min(max(3 * ram, 4), vol / 8), initial)
    return {"ram": round(ram, 1), "peak": round(peak, 1), "initial": round(initial), "max": round(maximum)}
