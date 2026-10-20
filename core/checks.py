"""Health checks for the dashboard. Each issue: title, detail, fix (callable or None)."""
from . import games, gpu, hardware, tweaks
from .i18n import t

def run(manual_games=()):
    issues = []
    try:
        if len(hardware.ram_modules()) == 1:
            issues.append((t("Single-channel RAM"), t("Only one memory module found. A second matching module "
                           "enables dual-channel and can raise FPS a lot, especially on laptops."), None))
    except Exception:
        pass
    try:
        cur, best, res = hardware.refresh_info()
        if best > cur:
            issues.append((t("Display at {hz} Hz", hz=cur), t("{res} supports {hz} Hz.", res=res, hz=best),
                           lambda: hardware.set_refresh(best)))
    except Exception:
        pass
    try:
        on_hdd = [g["name"] for g in games.scan(manual_games) if g["kind"] == "HDD"]
        if on_hdd:
            names = ", ".join(on_hdd[:3]) + (t(" and {n} more", n=len(on_hdd) - 3) if len(on_hdd) > 3 else "")
            issues.append((t("{n} game(s) on a hard drive", n=len(on_hdd)),
                           t("{names}. Games load faster from an SSD.", names=names), None))
    except Exception:
        pass
    if tweaks.state("Game Mode") == "off":
        issues.append((t("Game Mode is off"), t("Game Mode stops driver installs and restart prompts while gaming."),
                       lambda: tweaks.apply("Game Mode", True)))
    if not gpu.windowed_opt():
        issues.append((t("Windowed game optimization is off"), t("Lower latency, Auto HDR and VRR for DX10/11 "
                       "games in windowed or borderless mode."), lambda: gpu.set_windowed_opt(True)))
    if tweaks.hvci_state() == "off":
        issues.append((t("Memory integrity is off"), t("Your PC is less protected against malicious drivers. "
                       "Turn it back on when you are done gaming."), tweaks.open_core_isolation))
    if hardware.rebar() == "off":
        issues.append((t("Resizable BAR is off"), t("Enable it in BIOS if your board and GPU support it. "
                       "The gain depends on the game."), None))
    return issues
