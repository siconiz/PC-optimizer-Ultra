"""GPU status (NVIDIA), per-app GPU preference, windowed-game optimization."""
import shutil, subprocess
from .reg import HKCU, get, set_value, values

PREF_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"
GLOBAL = "DirectXUserGlobalSettings"
PREFS = {"Let Windows decide": 0, "Power saving": 1, "High performance": 2}
FIELDS = "name,temperature.gpu,utilization.gpu,clocks.gr,power.draw"

def _smi(fmt):
    if not shutil.which("nvidia-smi"):
        return None
    return subprocess.run(["nvidia-smi", f"--query-gpu={FIELDS}", f"--format={fmt}"],
                          capture_output=True, text=True, creationflags=0x08000000).stdout.strip()

def nvidia_status():
    return _smi("csv") or "nvidia-smi not found (no NVIDIA driver / non-NVIDIA GPU)."

def nvidia_metrics():
    out = _smi("csv,noheader,nounits")
    if not out:
        return None
    name, temp, util, clk, pwr = [x.strip() for x in out.splitlines()[0].split(",")]
    num = lambda s: float(s) if s.replace(".", "", 1).isdigit() else None
    return {"name": name, "temp": num(temp), "util": num(util), "clock": num(clk), "power": num(pwr)}

def set_app_pref(exe_path, level):
    set_value(HKCU, PREF_KEY, exe_path, f"GpuPreference={level};")

def list_app_prefs():
    return {k: v for k, v in values(HKCU, PREF_KEY).items() if k != GLOBAL}

WINDOWED, VRR = "SwapEffectUpgradeEnable", "VRROptimizeEnable"

def _global():
    return [p for p in (get(HKCU, PREF_KEY, GLOBAL) or "").split(";") if p]

def global_flag(name):
    return f"{name}=1" in _global()

def set_global_flag(name, on):
    # one string holds several Graphics settings; change only this entry
    parts = [p for p in _global() if not p.startswith(name + "=")] + [f"{name}={int(on)}"]
    set_value(HKCU, PREF_KEY, GLOBAL, ";".join(parts) + ";")

def windowed_opt():
    return global_flag(WINDOWED)

def set_windowed_opt(on):
    set_global_flag(WINDOWED, on)
