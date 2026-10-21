"""Computer scan: finds settings that are worse than they could be and offers the fix for each.
Only safe, reversible settings are pre-selected; the rest are shown as advice."""
import psutil
from . import desktop, disk, gpu, hardware, news, services, startup, tweaks
from .i18n import t

def _item(title, detail, fix=None, on=True, restart=False, kind=None):
    return {"title": title, "detail": detail, "fix": fix, "default": bool(fix) and on, "restart": restart, "kind": kind}

def run(cfg):
    out = []
    def safe(fn):
        try:
            fn()
        except Exception:
            pass
    def checks():
        if tweaks.state("Game Mode") == "off":
            out.append(_item(t("Turn on Game Mode"), t("Stops driver installs and restart prompts while gaming."),
                             lambda: tweaks.apply("Game Mode", True)))
        if tweaks.state("Background game recording") == "on":
            out.append(_item(t("Turn off background game recording"), t("Windows keeps recording the last minutes of "
                             "every game, which costs FPS. Win+Alt+R still records on demand."),
                             lambda: tweaks.apply("Background game recording", False)))
        if tweaks.state("Share updates with other PCs") != "off":
            out.append(_item(t("Stop sharing updates with other PCs"), t("Windows Update downloads only from Microsoft "
                             "and stops uploading updates to other PCs in the background."),
                             lambda: tweaks.apply("Share updates with other PCs", False), on=False))
        if not gpu.windowed_opt():
            out.append(_item(t("Turn on optimizations for windowed games"),
                             t("Lower latency, Auto HDR and VRR in windowed and borderless games."),
                             lambda: gpu.set_windowed_opt(True)))
        if tweaks.state("HW-accelerated GPU scheduling") == "off":
            out.append(_item(t("Turn on hardware-accelerated GPU scheduling"), t("Restart required."),
                             lambda: tweaks.apply("HW-accelerated GPU scheduling", True), restart=True))
    def display():
        cur, best, res = hardware.refresh_info()
        if best > cur:
            out.append(_item(t("Use {hz} Hz", hz=best), t("The display runs at {cur} Hz but supports {hz} Hz.",
                             cur=cur, hz=best), lambda: hardware.set_refresh(best)))
    def auto():
        if not cfg.get("autopilot", True):
            out.append(_item(t("Turn on Auto optimize"), t("Maximum performance only while a game runs, background "
                             "apps in efficiency mode."), lambda: cfg.__setitem__("autopilot", True)))
    def tips():
        on = [n for n in desktop.TIPS if desktop.tip_on(n)]
        if on:
            out.append(_item(t("Turn off Windows tips and suggestions"), ", ".join(t(n) for n in on),
                             lambda: [desktop.set_tip(n, False) for n in on]))
    def effects():
        if desktop.effects()["Transparency"]:
            out.append(_item(t("Turn off transparency effects"), t("Saves a little GPU work. Windows looks flatter."),
                             lambda: desktop.set_effect("Transparency", False), on=False))
    def boot():
        n = sum(e["enabled"] for e in startup.entries())
        if n > 8:
            out.append(_item(t("{n} apps start with Windows", n=n), t("Turn off the ones you do not need on the "
                             "System > Startup tab. Fewer startup apps means a faster sign-in.")))
    def space():
        u = psutil.disk_usage("C:\\")
        if u.free / u.total < 0.1:
            out.append(_item(t("Drive C: is almost full"), t("{gb} GB free. Windows and SSDs slow down when the system "
                             "drive is nearly full. Use the Cleanup page.", gb=round(u.free / 2**30))))
    def drives():
        for d in disk.health():
            if d["health"] != "Healthy" or (d["wear"] or 0) >= 80 or d["errors"]:
                out.append(_item(t("Drive needs attention: {name}", name=d["name"]),
                                 t("Health: {h}, wear {w}%. Back up your files.", h=t(d["health"]), w=d["wear"] or 0)))
    def ram():
        if len(hardware.ram_modules()) == 1:
            out.append(_item(t("Single-channel RAM"), t("A second matching module enables dual-channel and can raise "
                             "FPS a lot, especially on laptops.")))
    def feeds():
        if not news.is_off():
            out.append(_item(t("Stop background news"), t("Windows Widgets and Edge's new tab page stop loading news "
                             "in the background."), lambda: news.set_off(True)))
    def svc():
        missing = [n for n in services.SERVICES if n not in cfg.get("game_services", [])]
        if missing:
            out.append(_item(t("Pause unneeded services during games"), ", ".join(t(services.SERVICES[n][0])
                             for n in missing) + ". " + t("Started again when the game closes."),
                             lambda: cfg.__setitem__("game_services", list(services.SERVICES)), on=False))
    def power():
        out.append(_item(t("When the power mode changes"), t("Only while a game or a boost-list app runs (the "
                         "mode you had comes back afterwards), or also when the charger is connected or removed."),
                         lambda: None, kind="power"))
    for fn in (checks, display, auto, tips, effects, feeds, svc, power, boot, space, drives, ram):
        safe(fn)
    return out

def apply(items):
    """Runs the fixes; returns (done, failed, restart_needed)."""
    done, failed, restart = 0, 0, False
    for it in items:
        try:
            it["fix"]()
            done += 1
            restart |= it["restart"]
        except Exception:
            failed += 1
    return done, failed, restart
