"""Hardware report: RAM modules, display refresh rate, Resizable BAR (NVIDIA)."""
import re, shutil, subprocess
import win32api, win32con

def ram_modules():
    import wmi
    return [{"slot": m.DeviceLocator, "gb": int(m.Capacity) // 2**30,
             "mhz": m.ConfiguredClockSpeed, "part": (m.PartNumber or "").strip()}
            for m in wmi.WMI().Win32_PhysicalMemory()]

def refresh_info():
    """(current_hz, best_hz_at_current_resolution, resolution) for the primary display."""
    cur = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
    best = cur.DisplayFrequency
    for i in range(2000):
        try:
            m = win32api.EnumDisplaySettings(None, i)
        except Exception:
            break
        if (m.PelsWidth, m.PelsHeight) == (cur.PelsWidth, cur.PelsHeight):
            best = max(best, m.DisplayFrequency)
    return cur.DisplayFrequency, best, f"{cur.PelsWidth}x{cur.PelsHeight}"

def set_refresh(hz):
    dm = win32api.EnumDisplaySettings(None, win32con.ENUM_CURRENT_SETTINGS)
    dm.DisplayFrequency = hz
    dm.Fields = win32con.DM_DISPLAYFREQUENCY
    return win32api.ChangeDisplaySettings(dm, win32con.CDS_UPDATEREGISTRY) == win32con.DISP_CHANGE_SUCCESSFUL

def rebar():
    """'on' / 'off' / None (no NVIDIA). BAR1 total of 256 MiB means off."""
    if not shutil.which("nvidia-smi"):
        return None
    out = subprocess.run(["nvidia-smi", "-q", "-d", "MEMORY"], capture_output=True, text=True,
                         creationflags=0x08000000).stdout
    m = re.search(r"BAR1 Memory Usage\s+Total\s*:\s*(\d+)", out)
    return None if not m else ("on" if int(m.group(1)) > 256 else "off")
