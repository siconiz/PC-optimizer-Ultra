"""PC details (board, BIOS, model, CPU, RAM slots) and links to the maker's spec page / benchmark sites."""
import platform, urllib.parse
import psutil

LAPTOP_CHASSIS = {8, 9, 10, 11, 12, 14, 18, 21, 30, 31, 32}  # SMBIOS chassis types: portable, laptop, notebook...
MAKER_SITES = {"asus": "asus.com", "asustek": "asus.com", "msi": "msi.com", "micro-star": "msi.com",
               "gigabyte": "gigabyte.com", "asrock": "asrock.com", "lenovo": "psref.lenovo.com", "dell": "dell.com",
               "hp": "hp.com", "hewlett": "hp.com", "acer": "acer.com", "samsung": "samsung.com", "lg": "lg.com",
               "razer": "razer.com", "microsoft": "microsoft.com", "biostar": "biostar.com.tw", "evga": "evga.com",
               "nzxt": "nzxt.com", "framework": "frame.work", "huawei": "consumer.huawei.com", "xiaomi": "mi.com"}
GENERIC = {"", "to be filled by o.e.m.", "default string", "system product name", "system manufacturer",
           "not applicable", "none", "o.e.m.", "base board"}

def _clean(s):
    s = (s or "").strip()
    return "" if s.lower() in GENERIC else s

def _first(c, cls):
    try:
        return getattr(c, cls)()[0]
    except Exception:
        return None

def _get(obj, attr, default=""):
    try:
        return getattr(obj, attr) if obj is not None else default
    except Exception:  # missing property or COM error
        return default

def details():
    import wmi
    c = wmi.WMI()
    cs, board, bios, cpu = (_first(c, n) for n in ("Win32_ComputerSystem", "Win32_BaseBoard", "Win32_BIOS",
                                                    "Win32_Processor"))
    chassis, slots, mods = set(), 0, []
    try:
        for e in c.Win32_SystemEnclosure():
            chassis.update(e.ChassisTypes or ())
    except Exception:
        pass
    try:
        slots = sum(int(a.MemoryDevices or 0) for a in c.Win32_PhysicalMemoryArray() if a.Use == 3)  # system memory
        mods = [{"slot": m.DeviceLocator, "gb": int(m.Capacity) // 2**30, "mhz": m.ConfiguredClockSpeed or m.Speed,
                 "maker": _clean(m.Manufacturer), "part": _clean(m.PartNumber)} for m in c.Win32_PhysicalMemory()]
    except Exception:
        pass
    date = str(_get(bios, "ReleaseDate") or "")[:8]
    ver = _clean(_get(bios, "SMBIOSBIOSVersion"))
    return {"laptop": bool(chassis & LAPTOP_CHASSIS) or psutil.sensors_battery() is not None,
            "maker": _clean(_get(cs, "Manufacturer")), "model": _clean(_get(cs, "Model")),
            "family": _clean(_get(_first(c, "Win32_ComputerSystemProduct"), "Version")),  # e.g. "ThinkPad X1 Carbon Gen 11"
            "board_maker": _clean(_get(board, "Manufacturer")), "board": _clean(_get(board, "Product")),
            "bios": f"{ver} ({date[:4]}-{date[4:6]}-{date[6:]})" if len(date) == 8 and date.isdigit() else ver,
            "cpu": (_get(cpu, "Name") or platform.processor()).strip(), "cores": _get(cpu, "NumberOfCores", None)
            or psutil.cpu_count(False), "threads": _get(cpu, "NumberOfLogicalProcessors", None) or psutil.cpu_count(),
            "ram_gb": round(psutil.virtual_memory().total / 2**30, 1), "slots": slots, "modules": mods}

def site_for(maker):
    m = (maker or "").lower()
    return next((site for key, site in MAKER_SITES.items() if key in m), "")

def _search(q, site=""):
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(f"{q} site:{site}" if site else q)

def spec_link(info):
    """Search the maker's own site: the laptop/PC model if it is a branded PC, else the motherboard."""
    branded = info["laptop"] or site_for(info["maker"]) not in ("", site_for(info["board_maker"]))
    if branded and info["model"]:
        return _search(f"{info['family'] or info['model']} specifications", site_for(info["maker"]))
    return _search(f"{info['board']} specifications", site_for(info["board_maker"]))

def bench_links(cpu, gpus, ram_part=""):
    """External comparison pages (PassMark). Their data cannot be redistributed, so we only link to them."""
    out = [("CPU", _search(cpu, "cpubenchmark.net"))]
    out += [("GPU", _search(g, "videocardbenchmark.net")) for g in gpus]
    if ram_part:
        out.append(("RAM", _search(ram_part, "memorybenchmark.net")))
    return out
