"""Main window: sidebar navigation, pages built (and their modules imported) on first visit."""
import ctypes, importlib, os, queue, sys, time, webbrowser
import customtkinter as ctk
from core import config, update
from core.i18n import t
from core.version import REPO
from .kit import Kit, tip
from .theme import ACCENT, BG, CARD, CARD2, HOVER2, MODE, MUTED, SEL, SEL_H, SIDE, TEXT, F, pick_fonts

REPO_URL = f"https://github.com/{REPO}"
SPONSOR_URL = f"https://github.com/sponsors/{REPO.split('/')[0]}"

def _graphics(app, p):
    from . import gpudrv_ui, pages
    pages.graphics(app, p)
    gpudrv_ui.page(app, p)
    pages.cooling(app, p)

def _cleanup(app, p):
    from . import pages
    pages.storage(app, p)
    pages.browser_cache(app, p)

def _system(app, p):
    from . import pages, system
    tabs = [("Windows", pages.windows), ("Startup", system.startup_tab), ("Notifications & effects", system.desktop_tab),
            ("Browsers", pages.browser_policies), ("Hardware", pages.hardware_page)]
    frames = {}
    def show(label):
        key = next(k for k, _ in tabs if t(k) == label)
        if key not in frames:
            frames[key] = ctk.CTkFrame(p, fg_color="transparent", height=1)
            dict(tabs)[key](app, frames[key])
            app.background.paint(frames[key])
        for k, f in frames.items():
            f.pack(fill="x") if k == key else f.pack_forget()
    seg = app.seg(app.row(p, (0, 4)), [t(k) for k, _ in tabs], show)
    seg.pack(side="left", padx=4)
    seg.set(t("Windows"))
    show(t("Windows"))

def _lazy(module, fn):
    def build(app, p):
        getattr(importlib.import_module(f"ui.{module}"), fn)(app, p)
    return build

# (key, icon, builder): a page's module is imported only when the page is opened the first time
PAGES = [("Dashboard", "home", _lazy("widgets", "dashboard")), ("App management", "apps", _lazy("boost", "page")),
         ("AI optimization", "robot", _lazy("ai", "page")), ("CPU & Memory", "cpu", _lazy("cpumem", "page")),
         ("Graphics & Cooling", "monitor", _graphics), ("Overlay", "overlay", _lazy("overlay_ui", "page")),
         ("Diagnostics", "diag", _lazy("diag", "page")), ("Cleanup", "broom", _cleanup),
         ("System", "settings", _system), ("About", "info", _lazy("pages", "about"))]

def asset(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "assets", name)

class App(ctk.CTk, Kit):
    def __init__(self, cfg):
        super().__init__(fg_color=BG)
        self.cfg, self.q, self.watcher, self.current = cfg, queue.Queue(), None, None
        pick_fonts(self, __import__("core.i18n", fromlist=["LANG"]).LANG[0], cfg.get("font"))
        self.title("PC Optimizer")
        self.geometry("1180x760")
        self.minsize(1000, 640)
        if os.path.exists(asset("icon.ico")):
            self.after(300, self._icon)  # after customtkinter sets its own
        self.after(50, self._win11_frame)
        self.table_style()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar()
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(8, 20), pady=(16, 12))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)
        self.header = ctk.CTkLabel(self.content, text="", font=F(28, "bold"), text_color=TEXT, anchor="w")
        self.header.grid(row=0, column=0, sticky="w", padx=4, pady=(0, 10))
        self.builders, self.pages = {k: b for k, _, b in PAGES}, {}
        from .bgimage import Background
        self.background = Background(self)
        self.autopilot, self.app_index, self.game_exes, self.autopilot_lines, self.hw = None, [], set(), [], None
        from .overlay import Overlay
        self.overlay = Overlay(self)
        self.show("Dashboard")
        self.after(100, self._pump)
        self.after(400, self._start_workers)  # window first, background work after
        if os.environ.get("PCO_TIMING"):  # start-up time to the first drawn frame, for testing
            self.after_idle(lambda: open(os.environ["PCO_TIMING"], "w").write(
                f"{__import__('time').time() - __import__('psutil').Process().create_time():.2f}"))
        self.bind("<Configure>", self._on_configure, add="+")
        from .kit import Tooltips
        self.tooltips = Tooltips(self)
        self.protocol("WM_DELETE_WINDOW", self._close)
        if cfg.get("check_updates", True):
            self.after(3000, self.check_update)

    def _start_workers(self):
        if self.cfg.get("background", {}).get("path"):
            self.background._build()
        from core import appsdb
        cached = appsdb.load_cache()
        if cached:
            self._indexed(cached)
        self.bg(appsdb.scan, self._indexed, lambda m: None)
        if self.cfg.get("autopilot", True):
            self.set_autopilot(True)
        if self.cfg.get("sensors", True):
            self.after(1500, lambda: self.set_sensors(True))  # .NET start-up is the slowest part; do it last
        self.hotkey = None
        self.restart_hotkey()
        if self.cfg.get("overlay", {}).get("on"):
            self.after(2000, self.start_overlay)
        self._queue = [k for k, _, _ in PAGES if k != self.current]
        self.after(2500, self._prebuild)

    def _prebuild(self):
        """Build the other pages one by one while nothing else happens, so opening them later is instant."""
        if not self._queue:
            return
        if self.moving() or time.monotonic() - getattr(self, "_shown_at", 0) < 1.0:
            return self.after(500, self._prebuild)
        key = self._queue.pop(0)
        try:
            self._ensure(key)
        except Exception:
            pass
        self.after(300, self._prebuild)

    def _win11_frame(self):
        """Rounded corners and a title bar that matches the theme (Windows 11 DWM attributes)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            dwm = ctypes.windll.dwmapi
            dark = ctypes.c_int(1 if MODE[0] == "dark" else 0)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)     # DWMWA_USE_IMMERSIVE_DARK_MODE
            corner = ctypes.c_int(2)                                       # DWMWCP_ROUND
            dwm.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), 4)   # DWMWA_WINDOW_CORNER_PREFERENCE
            r, g, b = (int(BG[i:i + 2], 16) for i in (1, 3, 5))
            caption = ctypes.c_int(r | g << 8 | b << 16)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)  # DWMWA_CAPTION_COLOR
        except Exception:
            pass

    def _icon(self):
        try:
            self.iconbitmap(asset("icon.ico"))
        except Exception:
            pass

    def save(self):
        config.save(self.cfg)

    def _sidebar(self):
        s = ctk.CTkFrame(self, fg_color=SIDE, corner_radius=0, width=220)
        s.grid(row=0, column=0, sticky="ns")
        s.grid_propagate(False)
        ctk.CTkLabel(s, text="PC Optimizer", font=F(20, "bold"), text_color=ACCENT).pack(anchor="w", padx=20, pady=(24, 2))
        ctk.CTkLabel(s, text=t("Performance toolkit"), font=F(12), text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 16))
        self.nav = {}
        for key, _, _ in PAGES:
            b = ctk.CTkButton(s, text=t(key), anchor="w", height=34, corner_radius=10, font=F(14),
                              fg_color="transparent", text_color=MUTED,
                              hover_color=HOVER2 if self.cfg.get("background", {}).get("path") else CARD2,
                              command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=1)
            self.nav[key] = b
        self.boost_pill = ctk.CTkLabel(s, text=t("Auto optimize: off"), font=F(12), text_color=MUTED,
                                       fg_color=CARD, corner_radius=8, height=30)
        self.boost_pill.pack(side="bottom", fill="x", padx=12, pady=(4, 16))
        ctk.CTkButton(s, text=t("Support this project"), height=30, corner_radius=8, font=F(12),
                      fg_color="transparent", hover_color=CARD2, text_color=MUTED, border_width=1, border_color=CARD2,
                      command=lambda: webbrowser.open(SPONSOR_URL)).pack(side="bottom", fill="x", padx=12, pady=4)
        self.update_btn = ctk.CTkButton(s, text="", height=30, corner_radius=8, font=F(12, "bold"),
                                        fg_color=SEL, hover_color=SEL_H, text_color=ACCENT)

    def _ensure(self, key):
        if key not in self.pages:
            f = ctk.CTkScrollableFrame(self.content, fg_color=BG, corner_radius=0)
            self.pages[key] = f
            prev, self.current = self.current, key
            try:
                self.builders[key](self, f)
            finally:
                self.current = prev
            self.background.paint(f)

    def show(self, key):
        self._shown_at = time.monotonic()
        if key in getattr(self, "_queue", []):
            self._queue.remove(key)
        self._ensure(key)
        self.current = key
        pill = HOVER2 if self.cfg.get("background", {}).get("path") else CARD2  # stands out over a picture too
        for k, b in self.nav.items():
            on = k == key
            b.configure(fg_color=pill if on else "transparent", text_color=TEXT if on else MUTED)
            if on:
                self.pages[k].grid(row=1, column=0, sticky="nsew")
            elif k in self.pages:
                self.pages[k].grid_forget()
        self.header.configure(text=t(key))
        self.after(50, self.background.place)

    def _on_configure(self, e):
        if e.widget is self:  # the window itself moved or changed size (children also send <Configure>)
            pos = (e.x, e.y, e.width, e.height)
            if pos != getattr(self, "_geom", None):
                self._geom, self._moved_at = pos, __import__("time").monotonic()

    def _pump(self):
        if self.moving():  # finish the drag first; queued updates follow a moment later
            self.after(150, self._pump)
            return
        while not self.q.empty():
            try:
                self.q.get()()
            except Exception:
                pass
        self.after(100, self._pump)

    def _indexed(self, apps):
        self.app_index = apps
        self.refresh_games()

    def refresh_games(self):
        """Game exe names: Steam / Epic games and apps the user marked, minus apps marked as not a game."""
        marks = self.cfg.get("game_marks", {})
        names = set()
        for a in self.app_index:
            key = (a["exe"] or a["name"]).lower()
            if a["exe"] and marks.get(key, a["game"]):
                names.add(os.path.basename(a["exe"]).lower())
        self.game_exes.clear()
        self.game_exes.update(names)

    def log_autopilot(self, msg):
        line = f"{__import__('datetime').datetime.now():%H:%M:%S}  {msg}"
        self.autopilot_lines = (self.autopilot_lines + [line])[-200:]
        box = getattr(self, "autopilot_log", None)
        if box is not None and box.winfo_exists():
            self.write(box, line)

    def set_autopilot(self, on):
        if on and not self.autopilot:
            from core.auto import Autopilot
            self.autopilot = Autopilot(self.cfg, self.game_exes, lambda m: self.ui(lambda: self.log_autopilot(m)),
                                       lambda: self.ui(self._game_closed), lambda: self.ui(self._game_started))
            self.autopilot.start()
            self.boost_pill.configure(text=t("Auto optimize: on"), text_color=ACCENT)
        elif not on and self.autopilot:
            self.autopilot.stop()
            self.autopilot = None
            self.boost_pill.configure(text=t("Auto optimize: off"), text_color=MUTED)

    def start_overlay(self):
        self.overlay.show()

    def _overlay_key(self):
        if self.overlay.edit:
            self.overlay.set_edit(False)
        else:
            self.overlay.toggle()

    def restart_hotkey(self):
        from .overlay import Hotkey, cfg_of
        if self.hotkey:
            self.hotkey.stop()
        self.hotkey = Hotkey(self, cfg_of(self)["hotkey"], self._overlay_key)
        self.hotkey.start()

    def _game_started(self):
        from .overlay import cfg_of
        c = cfg_of(self)
        if c["auto"] and not self.overlay.win:
            self.overlay.show()
            self._auto_overlay = True

    def set_sensors(self, on):
        """Temperatures / fans through LibreHardwareMonitorLib; runs in its own thread."""
        if on and not self.hw:
            from core.sensors import Hardware
            self.hw = Hardware(self.cfg)
            self.hw.start()
        elif not on and self.hw:
            self.hw.stop()
            self.hw = None

    def _game_closed(self):
        """After a game boot, offer to turn memory integrity back on as soon as the game closes."""
        if getattr(self, "_auto_overlay", False):  # hide the overlay we opened for this game
            self._auto_overlay = False
            if not self.cfg.get("overlay", {}).get("on"):
                self.overlay.hide()
        if not self.cfg.get("game_boot"):
            return
        from core import gameboot
        if self.ask(t("Game boot"), t("The game has closed. Turn memory integrity back on now? It takes effect after a "
                    "restart.\n\nYes: restart now.  No: remind me later."), warn=False):
            gameboot.finish(self.cfg, restart=True)
            self.save()

    def _close(self):
        if getattr(self, "overlay", None):
            self.overlay.hide()
        for worker in (self.autopilot, self.hw):
            if worker:
                worker.stop()
                worker.join(timeout=3)  # fans go back to BIOS control here
        self.destroy()

    def check_update(self, manual=False, label=None):
        def done(rel):
            if rel:
                tag, url = rel
                self.update_btn.configure(text=t("Update available: {tag}", tag=tag), command=lambda: webbrowser.open(url))
                self.update_btn.pack(side="bottom", fill="x", padx=12, pady=4)
            if label is not None and label.winfo_exists():
                label.configure(text=t("{tag} is available.", tag=rel[0]) if rel else t("You have the latest version."))
        def fail(msg):
            if label is not None and label.winfo_exists():
                label.configure(text=t("Could not reach GitHub."))
        self.bg(update.newer_release, done, fail if manual else (lambda m: None))
