"""Windows / GPU registry tweaks. Each: ([(root, path, name), ...], on, off, restart_needed)."""
import os
from .reg import HKCU, HKLM, delete, get, set_value, values

GAMEDVR = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
EDGE = r"SOFTWARE\Policies\Microsoft\Edge"
CHROME = r"SOFTWARE\Policies\Google\Chrome"
DO = r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization"
TWEAKS = {
    "Game Mode": ([(HKCU, r"Software\Microsoft\GameBar", "AutoGameModeEnabled")], 1, 0, False),
    "HW-accelerated GPU scheduling": ([(HKLM, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode")],
                                      2, 1, True),
    "Background game recording": ([(HKCU, GAMEDVR, "HistoricalCaptureEnabled")], 1, 0, False),
    "Game Bar captures": ([(HKCU, GAMEDVR, "AppCaptureEnabled"), (HKCU, r"System\GameConfigStore", "GameDVR_Enabled")],
                          1, 0, False),
    "Share updates with other PCs": ([(HKLM, DO, "DODownloadMode")], 1, 0, False),
    "Edge startup boost": ([(HKLM, EDGE, "StartupBoostEnabled")], 1, 0, False),
    "Edge background mode": ([(HKLM, EDGE, "BackgroundModeEnabled")], 1, 0, False),
    "Edge sleeping tabs": ([(HKLM, EDGE, "SleepingTabsEnabled")], 1, 0, False),
    "Chrome background mode": ([(HKLM, CHROME, "BackgroundModeEnabled")], 1, 0, False),
    "Chrome Memory Saver": ([(HKLM, CHROME, "HighEfficiencyModeEnabled")], 1, 0, False),
}
HVCI = (HKLM, r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity", "Enabled")

def state(name):
    targets, on, off, _ = TWEAKS[name]
    vals = {get(*t) for t in targets}
    return "on" if vals == {on} else "off" if vals == {off} else "default"

def apply(name, enable):
    targets, on, off, restart = TWEAKS[name]
    for t in targets:
        set_value(*t, on if enable else off)
    return restart

def reset(names):
    """Remove the values so Windows / the browser uses its own default again."""
    for n in names:
        for t in TWEAKS[n][0]:
            delete(*t)

def hvci_state():
    return {1: "on", 0: "off"}.get(get(*HVCI), "default")

def hvci_disable():
    set_value(*HVCI, 0)  # restart required; re-enable from Windows Security UI

def open_core_isolation():
    os.startfile("windowsdefender://coreisolation")

def startup_entries():
    run = r"Software\Microsoft\Windows\CurrentVersion\Run"
    out = [("HKCU", n, v) for n, v in values(HKCU, run).items()]
    out += [("HKLM", n, v) for n, v in values(HKLM, run).items()]
    return out

def open_startup_settings():
    os.startfile("ms-settings:startupapps")
