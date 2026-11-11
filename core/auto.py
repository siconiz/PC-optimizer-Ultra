"""Autopilot: one background loop that
- switches to maximum performance while a game runs and back to the chosen mode when it closes,
- applies Boost list settings (priority, cores, AI mode) when those apps start,
- puts apps that are in the background into efficiency mode (optionally efficiency cores) and restores them
  when they come to the front. Apps in the exception list, games and Windows itself are never slowed down."""
import ctypes, os, threading
from ctypes import wintypes
import psutil
from . import cooling, procs, services
from .boost import resolve_cores
from .i18n import t
from .memory import PROTECTED
from .power import active_scheme, pc, ultimate_scheme

# power modes a listed app or game can ask for, strongest first; "Ultimate" = the Ultimate Performance plan
RUN_MODES = ["Ultimate", "Best performance", "Balanced", "Best power efficiency"]
DEFAULT_EXCEPTIONS = ["discord.exe", "obs64.exe", "teams.exe", "ms-teams.exe", "zoom.exe", "spotify.exe"]

def _name(pid):
    try:
        return psutil.Process(pid).name().lower() if pid else ""
    except (psutil.Error, OSError):
        return ""

def window_pids():
    """PIDs that own a visible top-level window (that is: user apps, not services)."""
    pids, user = set(), ctypes.windll.user32
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user.IsWindowVisible(hwnd) and user.GetWindowTextLengthW(hwnd):
            pid = wintypes.DWORD()
            user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pids.add(pid.value)
        return True
    user.EnumWindows(cb, 0)
    return pids

class Autopilot(threading.Thread):
    def __init__(self, cfg, game_exes, log, on_game_closed=None, on_game_started=None):
        super().__init__(daemon=True)
        self.cfg, self.game_exes, self.log, self.stop_evt = cfg, game_exes, log, threading.Event()
        self.on_game_closed, self.on_game_started = on_game_closed, on_game_started
        self.topo = procs.topology()

    def run(self):
        st = {"plan": None, "boosted": set(), "slowed": {}, "me": os.getpid(), "last_err": "", "lowered": set()}  # slowed: name -> pids
        self.log(t("Autopilot on"))
        try:
            while not self.stop_evt.wait(2):
                try:
                    self.step(st)
                except Exception as e:  # a process vanished mid-step etc.; try again next tick
                    if str(e) != st["last_err"]:
                        st["last_err"] = str(e)
                        self.log(str(e))
        finally:
            services.resume(st.get("services", []))
            for name, pids in st["slowed"].items():
                self._restore(list(pids))
                if name in st["lowered"]:
                    procs.set_priority(list(pids), "Normal")
            if st["plan"]:
                pc("/setactive", st["plan"])
            self.log(t("Autopilot off"))

    def step(self, st):
        saved_plan, boosted, slowed, me = st["plan"], st["boosted"], st["slowed"], st["me"]
        c = self.cfg
        profiles = {p["exe"]: p for p in c.get("boost", [])}
        games = set(self.game_exes) | {p["exe"] for p in profiles.values() if p.get("game")}
        # apps that switch the power mode: games and every app in the boost list (unless its plan option is off)
        triggers = games | {p["exe"] for p in profiles.values() if p.get("plan", True)}
        only_listed = c.get("power_only_listed", True)
        names = {}
        for p in psutil.process_iter(["name"]):
            names.setdefault((p.info["name"] or "").lower(), []).append(p.pid)
        # 1) game / listed app -> its power mode (the strongest of those running), afterwards the idle mode
        def wanted(exe):
            prof = profiles.get(exe)
            m = (prof or {}).get("power") or (c.get("game_power") if exe in games and not prof else None)
            return m if m in RUN_MODES else "Ultimate"
        running = triggers & names.keys()
        target = min((wanted(e) for e in running), key=RUN_MODES.index, default=None)
        game_on = target is not None
        bat = psutil.sensors_battery()
        plugged = bat is None or bool(bat.power_plugged)
        idle = self.idle_mode(plugged)
        max_on_battery = c.get("battery_game_max", True)
        if game_on and saved_plan is None:
            saved_plan = st["plan"] = active_scheme()
            st["mode"] = cooling.power_mode()
            if not (plugged or max_on_battery):
                self.log(t("Game started on battery: keeping {mode}", mode=t(idle)))
            if self.on_game_started:
                self.on_game_started()
            if c.get("game_trim", False):
                self.log(t("Freed {mb} MB of RAM for the game", mb=procs.free_ram(keep=list(games))))
            st["services"] = services.pause(c.get("game_services", []))
            if st["services"]:
                self.log(t("Paused during the game: {s}", s=", ".join(st["services"])))
            self.check_power()
        if game_on and target != st.get("target") and (plugged or max_on_battery):
            pc("/setactive", ultimate_scheme() if target == "Ultimate" else saved_plan)
            cooling.set_power_mode("Best performance" if target == "Ultimate" else target)
            self.log(t("Power mode for {apps}: {mode}", apps=", ".join(sorted(running)), mode=t(target)))
        st["target"] = target
        if not game_on and saved_plan:
            pc("/setactive", saved_plan)
            saved_plan = st["plan"] = None
            back = st.pop("mode", None) if only_listed else idle  # only listed apps: put back what was there
            if back:
                cooling.set_power_mode(back)
            idle = back or idle
            services.resume(st.pop("services", []))
            self.log(t("Game closed: {mode}", mode=t(idle)))
            if self.on_game_closed:
                self.on_game_closed()
        elif not game_on and not only_listed and st.get("plugged") != plugged and (st.get("plugged") is not None or
                                                               c.get("power_ac") or c.get("power_dc")):
            cooling.set_power_mode(idle)  # charger plugged in or out
            self.log((t("Charger connected: {mode}") if plugged else t("On battery: {mode}")).format(mode=t(idle)))
        st["plugged"] = plugged
        # 2) Boost list settings for new processes
        for exe, prof in profiles.items():
            new = [pid for pid in names.get(exe, []) if pid not in boosted]
            if new:
                procs.set_priority(new, prof["priority"])
                procs.set_cores(new, resolve_cores(prof["cores"], self.topo))
                boosted.update(new)
                self.log(t("{name}: priority {pri}, cores applied", name=prof["name"], pri=t(prof["priority"])))
                if prof.get("ai"):
                    self.log(t("AI mode: freed {mb} MB of RAM from background apps",
                               mb=procs.free_ram(keep=[exe])))
        boosted &= set(psutil.pids())
        # 3) background apps -> efficiency mode
        if c.get("throttle", True):
            fg = _name(procs.foreground_pid())
            keep = {e.lower() for e in c.get("exceptions", DEFAULT_EXCEPTIONS)} | games | set(profiles) | PROTECTED
            apps = {n for pid in window_pids() if pid != me and (n := _name(pid))}
            lower, lowered = game_on and c.get("game_priority", True), st["lowered"]
            for name in apps - keep - {fg}:
                pids = names.get(name, [])
                if pids and slowed.get(name) != set(pids):
                    procs.set_efficiency(pids, True)
                    if c.get("ecores") and self.topo["e"]:
                        procs.set_cores(pids, self.topo["e"])
                    slowed[name] = set(pids)
                if pids and lower and name not in lowered:  # while gaming: background apps also get less CPU time
                    procs.set_priority(pids, "Below normal")
                    lowered.add(name)
            for name in list(lowered):
                if not lower or name == fg or name not in slowed:
                    procs.set_priority(names.get(name, []), "Normal")
                    lowered.discard(name)
            for name in list(slowed):
                if name == fg or name not in apps or name in keep:
                    self._restore(names.get(name, []))
                    if name in lowered:
                        procs.set_priority(names.get(name, []), "Normal")
                        lowered.discard(name)
                    del slowed[name]
        st["plan"], st["boosted"] = saved_plan, boosted

    def idle_mode(self, plugged):
        """Power mode outside games: separate choices for charger and battery (fall back to the old single one)."""
        c = self.cfg
        return c.get("power_ac" if plugged else "power_dc") or c.get("idle_mode", "Balanced")

    def check_power(self):
        """Warn when the battery or the charger limits performance during a game."""
        b = psutil.sensors_battery()
        if not b:
            return
        if not b.power_plugged:
            self.log(t("On battery: the laptop limits CPU and GPU power. Plug in the charger for full performance."))
            return
        try:
            from .diag import Sampler
            s = Sampler()
            self.stop_evt.wait(2)
            limit = s.sample("", record=False)["limit_pct"]
        except Exception:
            return
        if limit is not None and limit < 90:
            self.log(t("Charging, but performance is limited to {p}%. Check the charger's wattage or run Lag while "
                       "charging on the System > Hardware tab.", p=round(limit)))

    def _restore(self, pids):
        procs.set_efficiency(pids, False)
        procs.set_cores(pids, list(range(self.topo["cpus"])))

    def stop(self):
        self.stop_evt.set()
