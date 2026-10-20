"""Per-app CPU cores, priority, efficiency mode (EcoQoS) and RAM trimming."""
import ctypes, os, struct
from ctypes import wintypes
import psutil
from .memory import PROTECTED

PRIORITIES = {"Low": "IDLE_PRIORITY_CLASS", "Below normal": "BELOW_NORMAL_PRIORITY_CLASS",
              "Normal": "NORMAL_PRIORITY_CLASS", "Above normal": "ABOVE_NORMAL_PRIORITY_CLASS",
              "High": "HIGH_PRIORITY_CLASS"}
_cache = {}

def topology():
    """{'cpus': n, 'p': [logical cpus on performance cores], 'e': [on efficiency cores]} (group 0 only)."""
    n = psutil.cpu_count() or 1
    try:
        k32 = ctypes.windll.kernel32
        size = wintypes.DWORD(0)
        k32.GetLogicalProcessorInformationEx(0, None, ctypes.byref(size))  # RelationProcessorCore
        buf = ctypes.create_string_buffer(size.value)
        if not k32.GetLogicalProcessorInformationEx(0, buf, ctypes.byref(size)):
            raise OSError
        cores, off = [], 0
        while off < size.value:
            rel_size = struct.unpack_from("<I", buf, off + 4)[0]
            eff = buf.raw[off + 9]
            mask, group = struct.unpack_from("<QH", buf, off + 32)
            if group == 0:
                cores.append((eff, [i for i in range(64) if mask >> i & 1]))
            off += rel_size
        top = max(e for e, _ in cores)
        if top == min(e for e, _ in cores):
            return {"cpus": n, "p": list(range(n)), "e": []}
        return {"cpus": n, "p": sorted(c for e, cs in cores if e == top for c in cs),
                "e": sorted(c for e, cs in cores if e != top for c in cs)}
    except Exception:
        return {"cpus": n, "p": list(range(n)), "e": []}

def apps():
    """Running apps grouped by name: cpu %, memory MB, pids. cpu % needs two calls a second apart."""
    out = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        proc = _cache.setdefault(p.pid, p)
        try:
            cpu = proc.cpu_percent(None)
        except (psutil.Error, OSError):
            continue
        name, mi = p.info["name"] or "?", p.info["memory_info"]
        a = out.setdefault(name, {"name": name, "cpu": 0.0, "mb": 0.0, "pids": []})
        a["cpu"] += cpu / (psutil.cpu_count() or 1)
        a["mb"] += (mi.rss if mi else 0) / 2**20
        a["pids"].append(p.pid)
    alive = set(psutil.pids())
    for pid in list(_cache):
        if pid not in alive:
            del _cache[pid]
    for a in out.values():
        a["protected"] = a["name"].lower() in PROTECTED
    return sorted(out.values(), key=lambda a: -(a["cpu"] * 50 + a["mb"]))

def _each(pids, fn):
    done = 0
    for pid in pids:
        try:
            fn(psutil.Process(pid))
            done += 1
        except (psutil.Error, OSError):
            pass
    return done

def set_cores(pids, cpus):
    return _each(pids, lambda p: p.cpu_affinity(list(cpus)))

def set_priority(pids, level):
    return _each(pids, lambda p: p.nice(getattr(psutil, PRIORITIES[level])))

class _Throttle(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]

def _open(pid, access):
    return ctypes.windll.kernel32.OpenProcess(access, False, pid)

def set_efficiency(pids, on):
    """Efficiency mode, same as Task Manager: EcoQoS (ProcessPowerThrottling, execution speed)."""
    k32, done = ctypes.windll.kernel32, 0
    st = _Throttle(1, 1, 1 if on else 0)
    for pid in pids:
        h = _open(pid, 0x0200)  # PROCESS_SET_INFORMATION
        if h:
            done += bool(k32.SetProcessInformation(h, 4, ctypes.byref(st), ctypes.sizeof(st)))
            k32.CloseHandle(h)
    return done

def trim(pids):
    """EmptyWorkingSet: moves the app's idle pages out of RAM. They come back from disk when used again."""
    k32, done = ctypes.windll.kernel32, 0
    for pid in pids:
        h = _open(pid, 0x1000 | 0x0100)  # QUERY_LIMITED_INFORMATION | SET_QUOTA
        if h:
            done += bool(k32.K32EmptyWorkingSet(h))
            k32.CloseHandle(h)
    return done

def foreground_pid():
    u = ctypes.windll.user32
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(u.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value

def free_ram(keep=()):
    """Trim background apps (not the foreground app, not `keep`, not Windows itself), then free standby memory.
    Returns MB of available memory gained."""
    from . import memory
    before = psutil.virtual_memory().available
    keep = {k.lower() for k in keep}
    fg, me = foreground_pid(), os.getpid()
    pids = [p.pid for p in psutil.process_iter(["name"])
            if p.pid not in (fg, me, 0, 4) and (p.info["name"] or "").lower() not in PROTECTED | keep]
    trim(pids)
    try:
        memory.purge_standby()
    except Exception:
        pass
    return round((psutil.virtual_memory().available - before) / 2**20)
