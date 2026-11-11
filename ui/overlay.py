"""In-game overlay: an always-on-top, click-through window with the modules the user turned on.
Works over windowed and borderless games; exclusive full-screen games may draw over it."""
import ctypes, datetime, os, threading, time, tkinter as tk
from ctypes import wintypes
import psutil
from core import gpuinfo, net, procs
from core.i18n import t
from . import theme

# id: (title, icon, on by default, what it shows / needs)
MODULES = {
    "sysinfo": ("System info", "info", False, "Resolution, CPU, RAM and graphics card names."),
    "fps": ("FPS", "speed", True, "Frames per second of the app in front (Intel PresentMon)."),
    "avglow": ("Average & 1% low", "equalizer", True, "Average FPS and the 1% low (the slowest frames) since the game "
               "came to the front."),
    "fpsgraph": ("FPS graph", "diag", False, "FPS over the last frames."),
    "frametime": ("Frame time", "clock", False, "Time per frame in ms. Spikes are stutters."),
    "cpu": ("CPU", "cpu", True, "Clock, usage and temperature. Clock and temperature need PawnIO."),
    "gpu": ("GPU", "monitor", True, "Clock, usage and temperature."),
    "ram": ("RAM", "drive", True, "Memory in use."),
    "vram": ("VRAM", "monitor", False, "Graphics memory in use."),
    "cores": ("Per core", "cpu", False, "Clock, usage and temperature for each core. Core temperatures need PawnIO; "
              "most AMD Ryzen CPUs only report one temperature per CCD, so those rows show clock and usage."),
    "ping": ("Ping", "wifi", False, "Ping to the server the game is connected to, or to 1.1.1.1 if it cannot be found."),
    "gametime": ("Game time", "game", False, "How long the app in front has been running."),
    "clock": ("Clock", "clock", False, "Current time."),
    "mic": ("Microphone", "mic", False, "Shows when the microphone is muted."),
}
POSITIONS = ["tl", "tc", "tr", "bl", "br"]
SIZES = {"s": 12, "m": 15, "l": 19}   # base text size in px
BLUE, GREEN, ORANGE, GREY, WHITE, PURPLE = "#62b1ff", "#5bd16f", "#ffa14a", "#a8a8a8", "#ffffff", "#b39ddb"
MODS = {"Ctrl": 0x0002, "Shift": 0x0004, "Alt": 0x0001, "Win": 0x0008}
NAMED_KEYS = {"Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
              "Pause": 0x13, "ScrollLock": 0x91, "Space": 0x20, "Tab": 0x09}

def default_cfg():
    return {"on": False, "auto": True, "games_only": True, "modules": {k: v[2] for k, v in MODULES.items()},
            "order": list(MODULES), "pos": "tl", "x": 12, "y": 12, "monitor": 0, "size": "m", "box": 0.55,
            "detached": {}, "hotkey": "Ctrl+Shift+O", "presets": {}}

def cfg_of(app):
    c = app.cfg.setdefault("overlay", default_cfg())
    for k, v in default_cfg().items():
        c.setdefault(k, v)
    if len(c["hotkey"]) == 1:  # 1.0 stored only the letter after Ctrl+Shift
        c["hotkey"] = "Ctrl+Shift+" + c["hotkey"].upper()
    for k in MODULES:
        c["modules"].setdefault(k, MODULES[k][2])
        if k not in c["order"]:
            c["order"].append(k)
    return c

def parse_hotkey(combo):
    """'Ctrl+Shift+O' -> (modifier flags, virtual-key code) for RegisterHotKey, or None if it is not valid."""
    *mods, key = combo.split("+") if combo else [""]
    flags = 0
    for m in mods:
        if m not in MODS:
            return None
        flags |= MODS[m]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key[:1] == "F" and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    elif key in NAMED_KEYS:
        vk = NAMED_KEYS[key]
    else:
        return None
    if not flags and not (0x70 <= vk <= 0x87 or key in ("Pause", "ScrollLock", "Insert")):
        return None  # a plain letter alone would block typing in every app
    return flags, vk

def monitors():
    import win32api
    return [win32api.GetMonitorInfo(h)["Work"] for h, _, _ in win32api.EnumDisplayMonitors()]

class Hotkey(threading.Thread):
    """A global shortcut (RegisterHotKey) that calls fn on the UI thread. `ok` is False if another app owns it."""
    def __init__(self, app, combo, fn):
        super().__init__(daemon=True)
        self.app, self.combo, self.fn, self.tid, self.ok = app, combo, fn, None, None

    def run(self):
        u = ctypes.windll.user32
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        parsed = parse_hotkey(self.combo) or parse_hotkey("Ctrl+Shift+O")
        self.ok = bool(u.RegisterHotKey(None, 1, parsed[0] | 0x4000, parsed[1]))  # 0x4000 = MOD_NOREPEAT
        if not self.ok:
            return
        msg = wintypes.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                self.app.ui(self.fn)
        u.UnregisterHotKey(None, 1)

    def stop(self):
        if self.tid:
            ctypes.windll.user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)  # WM_QUIT

# ---------- drawing: one RGBA picture per box, shown with per-pixel transparency ----------
class _BMI(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]

def _gdi():
    g, u, P = ctypes.windll.gdi32, ctypes.windll.user32, ctypes.c_void_p
    for f, res, args in ((u.GetDC, P, [P]), (u.ReleaseDC, ctypes.c_int, [P, P]), (g.CreateCompatibleDC, P, [P]),
                         (g.CreateDIBSection, P, [P, P, ctypes.c_uint, P, P, ctypes.c_uint32]),
                         (g.SelectObject, P, [P, P]), (g.DeleteObject, ctypes.c_int, [P]), (g.DeleteDC, ctypes.c_int, [P]),
                         (u.UpdateLayeredWindow, ctypes.c_int, [P, P, P, P, P, P, ctypes.c_uint32, P, ctypes.c_uint32])):
        f.restype, f.argtypes = res, args
    return g, u

def update_layered(hwnd, img, x, y):
    """Show an RGBA picture as the window's content (UpdateLayeredWindow with per-pixel alpha). Nothing is painted
    by Tk, so the window never flashes while it changes."""
    from PIL import Image, ImageChops
    r, g_, b, a = img.split()
    pm = Image.merge("RGBA", [ImageChops.multiply(c, a) for c in (r, g_, b)] + [a])  # premultiplied alpha
    data = pm.tobytes("raw", "BGRA")
    gdi, user = _gdi()
    w, h = img.size
    screen = user.GetDC(None)
    mem = gdi.CreateCompatibleDC(screen)
    bits = ctypes.c_void_p()
    bmi = _BMI(ctypes.sizeof(_BMI), w, -h, 1, 32, 0)  # top-down 32-bit
    hbmp = gdi.CreateDIBSection(mem, ctypes.addressof(bmi), 0, ctypes.addressof(bits), None, 0)
    try:
        ctypes.memmove(bits, data, len(data))
        old = gdi.SelectObject(mem, hbmp)
        pt, size, src = wintypes.POINT(x, y), wintypes.SIZE(w, h), wintypes.POINT(0, 0)
        blend = (ctypes.c_ubyte * 4)(0, 0, 255, 1)  # AC_SRC_OVER, 0, alpha 255, AC_SRC_ALPHA
        ok = user.UpdateLayeredWindow(hwnd, screen, ctypes.addressof(pt), ctypes.addressof(size), mem,
                                      ctypes.addressof(src), 0, ctypes.addressof(blend), 2)  # ULW_ALPHA
        gdi.SelectObject(mem, old)
    finally:
        gdi.DeleteObject(hbmp)
        gdi.DeleteDC(mem)
        user.ReleaseDC(None, screen)
    return bool(ok)

_FONTS = {}
def _font(px, bold):
    """Segoe UI (Malgun Gothic for Korean, or the downloaded font) at a pixel size."""
    from PIL import ImageFont
    key = (px, bold, theme.FONT[0])
    if key not in _FONTS:
        local = os.path.join(os.environ.get("LOCALAPPDATA", ""), "PCOptimizer", "fonts")
        names = {"Pretendard": [os.path.join(local, "Pretendard-Bold.otf" if bold else "Pretendard-Regular.otf")],
                 "Malgun Gothic": ["malgunbd.ttf" if bold else "malgun.ttf"]}.get(theme.FONT[0], [])
        names += ["segoeuib.ttf" if bold else "segoeui.ttf", "malgunbd.ttf" if bold else "malgun.ttf",
                  "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
        for n in names:
            try:
                _FONTS[key] = ImageFont.truetype(n, px)
                break
            except OSError:
                continue
        else:
            _FONTS[key] = ImageFont.load_default(px)
    return _FONTS[key]

def draw_graph(vals, w, h, kind="fps", scale=3):
    """Smooth graph picture (RGBA, w x h): drawn 3x larger and scaled down for clean edges, soft fill under the
    line, guide lines with their values. kind 'fps' (higher is better) or 'ms' (frame time, spikes are bad)."""
    from PIL import Image, ImageDraw
    W, H, S = w * scale, h * scale, scale
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if len(vals) < 2:
        return img.resize((w, h), Image.LANCZOS)
    if kind == "fps" and len(vals) > 4:  # 3-point average: the trend without the sampling noise
        vals = [sum(vals[max(0, i - 1):i + 2]) / len(vals[max(0, i - 1):i + 2]) for i in range(len(vals))]
    top = max(vals)
    step = next((s for s in (5, 10, 20, 30, 50, 100) if top * 1.15 / s <= 4), 200)
    hi = max(step, step * -(-top * 1.15 // step))  # round up to a guide step
    avg = sum(vals) / len(vals)
    good = avg >= 60 if kind == "fps" else max(vals) <= 25
    ok = avg >= 30 if kind == "fps" else max(vals) <= 50
    col = (73, 220, 120) if good else (255, 200, 70) if ok else (255, 90, 80)
    d = ImageDraw.Draw(img)
    f = _font(max(8, h // 4) * S, False)
    for gv in (hi / 2, hi):  # guide lines
        gy = H - (H - 2 * S) * gv / hi
        d.line([(0, gy), (W, gy)], fill=(255, 255, 255, 40), width=S)
        d.text((W - 2 * S, gy + S), f"{gv:.0f}", font=f, fill=(255, 255, 255, 110), anchor="ra")
    pts = [(i * (W - 1) / (len(vals) - 1), H - S - (H - 3 * S) * min(v, hi) / hi) for i, v in enumerate(vals)]
    fill = Image.new("RGBA", (W, H), col + (0,))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(pts + [(W - 1, H), (0, H)], fill=255)
    grad = Image.linear_gradient("L").resize((W, H)).point(lambda v: (255 - v) * 90 // 255)  # 35% at top -> 0
    fill.putalpha(Image.composite(grad, Image.new("L", (W, H), 0), mask))
    img.alpha_composite(fill)
    d.line(pts, fill=col + (255,), width=2 * S, joint="curve")
    if kind == "ms":  # mark stutters: frames over twice the average frame time
        for (x, y), v in zip(pts, vals):
            if v > 2 * avg and v > 16:
                d.ellipse((x - 2 * S, y - 2 * S, x + 2 * S, y + 2 * S), fill=(255, 90, 80, 255))
    return img.resize((w, h), Image.LANCZOS)

def render(rows, base, box, edit):
    """rows: [[('t', text, color, size_step) | ('g', values, color)]] -> RGBA picture of one overlay box."""
    from PIL import Image, ImageDraw
    pad, gap, gw, gh = round(base * 0.6), round(base * 0.45), round(base * 15), round(base * 3.2)
    lines = []
    for row in rows:
        w = h = 0
        for it in row:
            if it[0] == "t":
                f = _font(base + it[3], True)
                w += f.getlength(it[1]) + gap
                h = max(h, round((base + it[3]) * 1.3))
            else:
                w, h = max(w, gw), max(h, gh + 2)
        lines.append((row, w - gap if row and row[-1][0] == "t" else w, h))
    W = int(max([w for _, w, _ in lines] + [base * 4]) + pad * 2)
    H = int(sum(h for _, _, h in lines) + pad * 2)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    alpha = max(box, 0.35) if edit else box  # in edit mode the box must be visible (and clickable)
    if alpha > 0:
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=pad, fill=(13, 13, 13, int(255 * alpha)),
                            outline=theme.ACCENT if edit else None, width=2 if edit else 0)
    stroke = 2 if box < 0.3 else 0  # without a box, an outline keeps text readable over a bright game
    y = pad
    for row, _, h in lines:
        x = pad
        for it in row:
            if it[0] == "t":
                size = base + it[3]
                d.text((x, y + h - size * 1.15), it[1], font=_font(size, True), fill=it[2],
                       stroke_width=stroke, stroke_fill=(0, 0, 0, 220))
                x += _font(size, True).getlength(it[1]) + gap
            else:
                img.alpha_composite(draw_graph(it[1], gw, gh, it[3] if len(it) > 3 else "fps"), (int(x), int(y + 1)))
        y += h
    return img

class Panel:
    """One overlay box: the main box or an item that has its own position."""
    def __init__(self, ov, key):
        self.ov, self.key, self.last, self.geom, self.layered = ov, key, None, None, True
        self.win = w = tk.Toplevel(ov.app)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg="#0d0d0d")
        self.label = None
        w.bind("<ButtonPress-1>", self._start)
        w.bind("<B1-Motion>", self._drag)
        w.bind("<ButtonRelease-1>", self._drop)
        w.geometry("1x1+-100+-100")
        w.update_idletasks()  # the window frame (whose handle we need) exists only after this
        self.tries = 0
        self.style(click_through=True)

    def hwnd(self):
        return int(self.win.wm_frame(), 16)

    def style(self, click_through):
        """LAYERED (per-pixel alpha) | TOOLWINDOW | NOACTIVATE, and TRANSPARENT so clicks reach the game."""
        try:
            u, h = ctypes.windll.user32, self.hwnd()
            st = u.GetWindowLongW(h, -20) | 0x80000 | 0x80 | 0x08000000
            u.SetWindowLongW(h, -20, st | 0x20 if click_through else st & ~0x20)
        except Exception:
            self.layered = False

    def show(self, img, x, y):
        w, h = img.size
        if (w, h, x, y) != self.geom:
            self.geom = (w, h, x, y)
            self.win.geometry(f"{w}x{h}+{x}+{y}")  # Tk's idea of the window, used for dragging
        if self.layered:
            try:
                if update_layered(self.hwnd(), img, x, y):
                    self.tries = 0
                    return
            except Exception:
                pass
            self.tries += 1
            if self.tries < 3:  # the window may not have been shown yet: set the style again and retry next tick
                self.win.update_idletasks()
                self.style(click_through=not self.ov.edit)
                return
            self.layered = False
        from PIL import Image, ImageTk  # fallback without per-pixel alpha
        flat = Image.alpha_composite(Image.new("RGBA", img.size, (13, 13, 13, 255)), img)
        self.photo = ImageTk.PhotoImage(flat)
        if self.label is None:
            self.label = tk.Label(self.win, bd=0, highlightthickness=0)
            self.label.pack()
            for ev, fn in (("<ButtonPress-1>", self._start), ("<B1-Motion>", self._drag),
                           ("<ButtonRelease-1>", self._drop)):
                self.label.bind(ev, fn)
        self.label.configure(image=self.photo)

    def topmost(self):
        try:  # HWND_TOPMOST, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            ctypes.windll.user32.SetWindowPos(self.hwnd(), -1, 0, 0, 0, 0, 0x2 | 0x1 | 0x10)
        except Exception:
            pass

    # edit mode: drag this box
    def _start(self, e):
        if self.ov.edit and self.geom:
            self._off = (e.x_root - self.geom[2], e.y_root - self.geom[3])

    def _drag(self, e):
        if self.ov.edit and getattr(self, "_off", None):
            self.ov.moved(self.key, e.x_root - self._off[0], e.y_root - self._off[1], save=False)

    def _drop(self, e):
        if self.ov.edit and getattr(self, "_off", None):
            self.ov.moved(self.key, e.x_root - self._off[0], e.y_root - self._off[1], save=True)
            self._off = None

    def destroy(self):
        self.win.destroy()

class Overlay:
    def __init__(self, app):
        self.app, self.edit, self.fps, self.panels, self.running = app, False, None, {}, False
        self.ping = {"ms": None, "host": ""}
        self.mic_muted, self.track_pid, self.track_since = None, None, time.time()
        self.usage, self.n = None, 0
        self.fps_hist, self.last_stats = __import__("collections").deque(maxlen=60), None
        self._ping_job = threading.Event()

    @property
    def win(self):  # kept for callers that check whether the overlay is showing
        return self.running or None

    def show(self):
        if self.running:
            return
        from core.fpsmon import FpsMonitor
        self.fps = FpsMonitor()
        self.fps.start()
        try:
            self.usage = gpuinfo.Usage()
        except Exception:
            self.usage = None
        self.running = True
        threading.Thread(target=self._ping_loop, daemon=True).start()
        self._tick()

    def hide(self):
        self.running = False
        if self.fps:
            self.fps.stop()
            self.fps = None
        self._ping_job.set()
        self._ping_job = threading.Event()
        for p in self.panels.values():
            p.destroy()
        self.panels = {}

    def toggle(self):
        c = cfg_of(self.app)
        c["on"] = not self.running
        self.app.save()
        self.show() if c["on"] else self.hide()

    def apply_style(self):
        """Redraw now (after a setting changed)."""
        for p in self.panels.values():
            p.last = None
        if self.running:
            self._render()

    def set_edit(self, on):
        self.edit = on
        if not self.running:
            self.show()
        for p in self.panels.values():
            p.style(click_through=not on)
        self.apply_style()

    # ---- where each box goes ----
    def _area(self):
        c = cfg_of(self.app)
        try:
            mons = monitors()
            return mons[min(c["monitor"], len(mons) - 1)]
        except Exception:
            return 0, 0, self.app.winfo_screenwidth(), self.app.winfo_screenheight()

    def _xy(self, key, w, h):
        c = cfg_of(self.app)
        left, top, right, bottom = self._area()
        if key != "main":
            d = c["detached"].get(key, {})
            return left + int(d.get("x", 12)), top + int(d.get("y", 200))
        if c["pos"] == "custom":
            return left + int(c["x"]), top + int(c["y"])
        m = 12
        x = {"l": left + m, "c": (left + right - w) // 2, "r": right - w - m}[c["pos"][1]]
        return x, (top + m if c["pos"][0] == "t" else bottom - h - m)

    def moved(self, key, x, y, save):
        """A box was dragged to screen position x, y: snap to the screen edges and remember it."""
        c = cfg_of(self.app)
        left, top, right, bottom = self._area()
        p = self.panels.get(key)
        w, h = (p.geom[0], p.geom[1]) if p and p.geom else (0, 0)
        x, y, snap = x - left, y - top, 24
        x = 12 if x < snap else (right - left - w - 12 if right - left - (x + w) < snap else x)
        y = 12 if y < snap else (bottom - top - h - 12 if bottom - top - (y + h) < snap else y)
        if key == "main":
            c.update(pos="custom", x=x, y=y)
        else:
            c["detached"][key] = {"x": x, "y": y}
        if p and p.last is not None:
            p.show(p.last[1], left + x, top + y)
        if save:
            self.app.save()

    # ---- data ----
    def _target(self):
        """Process in front, if it counts as a game (or any app when 'games only' is off)."""
        pid = procs.foreground_pid()
        try:
            name = psutil.Process(pid).name().lower()
        except (psutil.Error, OSError):
            return None
        if pid == __import__("os").getpid():
            return self.track_pid
        if cfg_of(self.app)["games_only"] and name not in self.app.game_exes:
            return self.track_pid
        return pid

    def _ping_loop(self):
        stop = self._ping_job
        while not stop.wait(3):
            if not cfg_of(self.app)["modules"].get("ping"):
                continue
            host = "1.1.1.1"
            try:
                if self.track_pid:
                    remotes = [c.raddr.ip for c in psutil.Process(self.track_pid).net_connections("inet")
                               if c.raddr and not c.raddr.ip.startswith(("127.", "10.", "192.168.", "::1", "fe80"))]
                    if remotes:
                        host = max(set(remotes), key=remotes.count)
                r = net.ping(host, 1, 800)
                if r["avg"] is None and host != "1.1.1.1":  # many game servers ignore ping
                    host, r = "1.1.1.1", net.ping("1.1.1.1", 1, 800)
                self.ping = {"ms": r["avg"], "host": host}
            except Exception:
                pass

    def _mic(self):
        try:
            import comtypes
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            mic = AudioUtilities.GetMicrophone()
            v = mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
            return bool(v.GetMute())
        except Exception:
            return None

    # ---- drawing ----
    def _tick(self):
        if not self.running:
            return
        try:
            pid = self._target()
            if pid != self.track_pid:
                self.track_pid, self.track_since = pid, time.time()
                try:
                    self.track_since = psutil.Process(pid).create_time() if pid else time.time()
                except (psutil.Error, OSError):
                    pass
            if self.fps:
                self.fps.track(pid)
            self._render()
            self.n += 1
            if self.n % 4 == 0:  # games sometimes push other windows down
                for p in self.panels.values():
                    p.topmost()
        except Exception:
            pass
        self.app.after(500, self._tick)

    def _render(self):
        c = cfg_of(self.app)
        st = self.fps.stats() if self.fps else None
        if st:
            self.fps_hist.append(st["fps"])
        self.last_stats = st
        hw = getattr(self.app, "hw", None)
        try:
            snap = self.app.cached(("gpu", id(self.usage)), lambda: gpuinfo.snapshot(self.usage), []) if self.usage else []
        except Exception:
            snap = []
        g = max(snap, key=lambda x: x["util"] or 0) if snap else None
        groups = {"main": []}
        for k in [k for k in c["order"] if c["modules"].get(k)]:
            rows = []
            line = lambda *parts: rows.append([("t", text, color, kk) for text, color, kk in parts if text])
            graph = lambda vals, color, kind="fps": rows.append([("g", vals, color, kind)])
            try:
                self._module(k, line, graph, st, hw, g, c)
            except Exception:
                pass  # one failing sensor must not hide the rest
            groups.setdefault(k if k in c["detached"] else "main", []).extend(rows)
        if self.edit:
            groups["main"].append([("t", t("Drag a box to move it. Press {k} or Done to finish.", k=c["hotkey"]),
                                    GREY, -3)])
        for key in list(self.panels):
            if key not in groups or not groups[key]:
                self.panels.pop(key).destroy()
        base = SIZES[c["size"]]
        for key, rows in groups.items():
            if not rows:
                continue
            p = self.panels.get(key)
            if p is None:
                p = self.panels[key] = Panel(self, key)
                p.style(click_through=not self.edit)
            sig = (repr(rows), base, c["box"], self.edit)
            if p.last is None or p.last[0] != sig:
                img = render(rows, base, float(c["box"]), self.edit)
                p.last = (sig, img)
            img = p.last[1]
            x, y = self._xy(key, *img.size)
            p.show(img, x, y)

    def _module(self, k, line, graph, st, hw, g, c):
        if k == "sysinfo":
            import win32api
            try:
                dm = win32api.EnumDisplaySettings(None, -1)
                res = f"{dm.PelsWidth}x{dm.PelsHeight} {dm.DisplayFrequency}Hz"
            except Exception:
                res = ""
            info = self.app.__dict__.get("_sysinfo_short") or ""
            line((res, BLUE, -1))
            if info:
                line((info, PURPLE, -1))
        elif k == "fps":
            line(("FPS", WHITE, 4), (str(st["fps"]) if st else "--", GREEN, 10))
        elif k == "avglow" and st:
            line((t("Avg"), GREY, -1), (str(st["avg"]), WHITE, 1), ("1% low", GREY, -1), (str(st["low1"]), ORANGE, 1))
        elif k in ("fpsgraph", "frametime") and st:
            # FPS: one value per update (twice a second, last 30 s); frame time: every frame, so stutters show
            vals = list(self.fps_hist) if k == "fpsgraph" else st["frametimes"][-120:]
            label = ("FPS", f"{st['fps']} fps") if k == "fpsgraph" else (t("FRAME TIME"), f"{st['ms']} ms")
            line((label[0], WHITE if k == "fpsgraph" else "#ffd75e", -2), (label[1], WHITE, -2))
            graph(vals, WHITE, "fps" if k == "fpsgraph" else "ms")
        elif k == "cpu":
            temp = hw.cpu_temp() if hw else None
            mhz = hw.cpu_clock() if hw else None
            line(("CPU", BLUE, 2), (f"{mhz} MHz" if mhz else "", WHITE, 0),
                 (f"{psutil.cpu_percent():.0f} %", WHITE, 0), (f"{temp:.0f} °C" if temp else "", WHITE, 0))
        elif k == "gpu" and g:
            mhz, temp = hw.gpu() if hw else (None, None)
            temp = temp or g["temp"]
            line(("GPU", GREEN, 2), (f"{mhz} MHz" if mhz else "", WHITE, 0),
                 (f"{g['util']:.0f} %" if g["util"] is not None else "", WHITE, 0),
                 (f"{temp:.0f} °C" if temp else "", WHITE, 0))
        elif k == "ram":
            m = psutil.virtual_memory()
            line(("RAM", PURPLE, 0), (f"{(m.total - m.available) / 2**30:.1f} / {m.total / 2**30:.0f} GB", WHITE, 0))
        elif k == "vram" and g and g["vram_used_gb"] is not None:
            line(("VRAM", GREEN, 0), (f"{g['vram_used_gb']} / {g['vram_gb']} GB", WHITE, 0))
        elif k == "cores":
            per = psutil.cpu_percent(percpu=True)
            rows = hw.cores() if hw else []
            n = max(1, len(rows))
            step = max(1, len(per) // n)
            if not rows:
                rows = [(f"Core {i + 1}", None, None) for i in range(len(per))]
                step = 1
            for i, (name, mhz, temp) in enumerate(rows):
                use = per[i * step:(i + 1) * step]
                line((f"Core {i + 1}", BLUE, 0), (f"{mhz} MHz" if mhz else "", WHITE, -1),
                     (f"{sum(use) / len(use):.0f} %" if use else "", WHITE, -1),
                     (f"{temp:.0f} °C" if temp else "", WHITE, -1))
        elif k == "ping":
            ms = self.ping["ms"]
            line(("Ping", GREY, 0), (f"{ms} ms" if ms is not None else "--", ORANGE if ms and ms > 80 else WHITE, 0))
        elif k == "gametime" and self.track_pid:
            s = int(time.time() - self.track_since)
            line((t("Game time"), GREY, -1), (f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}", WHITE, 0))
        elif k == "clock":
            line((datetime.datetime.now().strftime("%H:%M"), WHITE, 0))
        elif k == "mic":
            if int(time.time()) % 2 == 0 or self.mic_muted is None:
                self.mic_muted = self._mic()
            if self.mic_muted:
                line(("MIC " + t("muted"), "#ff5c5c", 0))
