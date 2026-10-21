"""Dashboard: This PC, computer scan, and a grid of widgets the user places anywhere, resizes and removes
(like iOS / iPad widgets: drag the title to move, drag the corner to resize, × removes a widget)."""
import os, threading, tkinter, webbrowser
from datetime import datetime
from tkinter import filedialog
import customtkinter as ctk
from core import addons, bench, games, gpuinfo, memory
from core.i18n import t
from . import widgets_extra as wx
from .theme import ACCENT, BORDER, CARD, CARD2, HOVER2, MUTED, TEXT, WARN, F, IF, icon

PRESENTMON_URL = "https://github.com/GameTechDev/PresentMon/releases"
COLS = 4
SPAN = {"s": 1, "m": 2, "l": 4}

UNIT = 110          # one grid row in px; widgets snap to 4 columns x UNIT rows
DEFAULT_H = {"clock": 3, "network": 2, "ssd": 3, "space": 2, "battery": 3, "games": 4, "fps": 4, "memory": 3,
             "gpu": 2, "wallpaper": 2, "display": 3, "audio": 4, "input": 4}

def dashboard(app, page):
    from . import dash
    dash.banner(app, page)
    dash.pc_card(app, page)
    dash.scan_card(app, page)
    bar = app.row(page, (10, 2))
    title = app.label(bar, t("Widgets"), 16, bold=True)
    title.pack(side="left", padx=4)
    app.add_menu = ctk.CTkOptionMenu(bar, values=["-"], height=30, font=F(13), dropdown_font=F(13), fg_color=CARD2,
                                     button_color=CARD2, button_hover_color=HOVER2, text_color=TEXT, corner_radius=8,
                                     command=lambda title: _add(app, title))
    app.add_menu.pack(side="right", padx=4)
    app.edit_btn = app.button(bar, t("Edit"), lambda: _set_edit(app, not app.widget_edit), primary=False, width=80)
    app.edit_btn.pack(side="right", padx=4)
    app.widget_edit = False
    app.tip(title, t("Edit (or hold the mouse on a widget's title): drag the title to put a widget anywhere on the "
                     "grid, drag the corner handle to resize it, and press × to remove it. Widgets marked (download) "
                     "are fetched once from GitHub."))
    app.dash = ctk.CTkFrame(page, fg_color="transparent", height=60)
    app.dash.pack(fill="x")
    app.dash.bind("<Configure>", lambda e: _layout(app) if getattr(app, "_dash_w", None) != e.width else None,
                  add="+")
    _render(app)

def _ids(app):
    return app.cfg.setdefault("widgets", [])   # nothing by default

def _boxes(app):
    """{id: {'x': column, 'y': row, 'w': columns, 'h': rows}} for every widget on the dashboard. Widgets saved by
    older versions (only a size, or s / m / l) are placed in the first free spot."""
    store = app.cfg.setdefault("widget_sizes", {})
    out = {}
    for wid in _ids(app):
        s = store.get(wid)
        if not isinstance(s, dict):
            s = {"w": SPAN[s or WIDGETS.get(wid, (None, None, "m"))[2]]}
        b = {"w": max(1, min(COLS, int(s.get("w", 2)))), "h": int(s.get("h") or DEFAULT_H.get(wid, 3))}
        b["h"] = max(1, min(8, b["h"]))
        if "x" in s and "y" in s:
            b.update(x=max(0, min(COLS - b["w"], int(s["x"]))), y=max(0, int(s["y"])))
        else:
            b.update(_free(out, b["w"], b["h"]))
        out[wid] = b
    _resolve(out, None)
    store.update({k: dict(v) for k, v in out.items()})
    return out

def _hit(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]

def _free(boxes, w, h):
    y = 0
    while True:
        for x in range(COLS - w + 1):
            cand = {"x": x, "y": y, "w": w, "h": h}
            if not any(_hit(cand, b) for b in boxes.values()):
                return {"x": x, "y": y}
        y += 1

def _resolve(boxes, moved):
    """Widgets that overlap get pushed down, the one just moved keeps its place; then every widget moves up into
    the space above it (like iOS), so removing or shrinking a widget closes the gap."""
    order = sorted(boxes, key=lambda k: (k != moved, boxes[k]["y"], boxes[k]["x"]))
    placed = []
    for k in order:
        b = boxes[k]
        while any(_hit(b, boxes[o]) for o in placed):
            b["y"] += 1
        placed.append(k)
    for k in sorted(boxes, key=lambda k: (boxes[k]["y"], boxes[k]["x"])):
        b = boxes[k]
        while b["y"] > 0 and not any(_hit(dict(b, y=b["y"] - 1), boxes[o]) for o in boxes if o != k):
            b["y"] -= 1

def _save_box(app, wid, **kw):
    boxes = _boxes(app)
    boxes[wid].update(kw)
    boxes[wid]["x"] = max(0, min(COLS - boxes[wid]["w"], boxes[wid]["x"]))
    _resolve(boxes, wid)
    app.cfg["widget_sizes"] = {k: dict(v) for k, v in boxes.items()}
    app.save()
    _render(app)

def _title(wid):
    if wid in WIDGETS:
        return t(WIDGETS[wid][0])
    name = t(addons.CATALOG[wid]["title"])
    return name if addons.installed(wid) else t("{name} (download)", name=name)

def _all():
    return list(WIDGETS) + addons.ids("widget")

def _set_edit(app, on):
    app.widget_edit = on
    app.edit_btn.configure(text=t("Done") if on else t("Edit"))
    _render(app)

def _render(app):
    for w in app.dash.winfo_children():
        w.destroy()
    ids = [w for w in _ids(app) if w in WIDGETS or w in addons.CATALOG]
    app.cfg["widgets"] = ids
    app.cells = {}
    for wid in ids:
        cell = ctk.CTkFrame(app.dash, fg_color="transparent")
        cell.pack_propagate(False)
        cell.wid = wid
        app.cells[wid] = cell
        body = app.card(cell, _title(wid))
        card = body.master
        if app.widget_edit:
            card.configure(border_width=2, border_color=ACCENT)
        _draggable(app, card.head, wid)
        try:
            WIDGETS[wid][1](app, body) if wid in WIDGETS else addons.load(wid).build(app, body)
        except Exception as e:
            app.label(body, t("This widget could not be loaded: {e}", e=e), 12, muted=True).pack(anchor="w")
        if app.widget_edit:
            _edit_handles(app, cell, card, wid)
    if not ids:
        hint = app.label(app.dash, t("No widgets yet. Use 'Add widget' to add one."), 13, muted=True)
        hint.place(relx=0.5, y=24, anchor="n")
    _layout(app)
    free = [_title(w) for w in _all() if w not in ids]
    app.add_menu.configure(values=free or [t("All widgets added")])
    app.add_menu.set("+ " + t("Add widget"))
    if getattr(app, "background", None):
        app.background.paint(app.dash)

def _layout(app):
    """Put every widget at its grid position (columns follow the window width)."""
    width = app.dash.winfo_width()
    app._dash_w = width
    boxes = _boxes(app)
    rows = max([b["y"] + b["h"] for b in boxes.values()] + [1])
    app.dash.configure(height=rows * UNIT)
    u = _unit(app)
    for wid, cell in getattr(app, "cells", {}).items():
        b = boxes.get(wid)
        if b and cell.winfo_exists():
            _place(cell, relx=b["x"] / COLS, relwidth=b["w"] / COLS, y=int(b["y"] * u), height=int(b["h"] * u))
    if getattr(app, "background", None):
        app.after(60, app.background.place)

class _Ghost:
    """Where a dragged widget will land: only an outline, so the widgets under it stay visible."""
    def __init__(self, parent):
        self.lines = [tkinter.Frame(parent, bg=ACCENT, bd=0, highlightthickness=0) for _ in range(4)]

    def put(self, x, y, width, height, t=2):
        for f, kw in zip(self.lines, (dict(x=x, y=y, width=width, height=t), dict(x=x, y=y + height - t, width=width,
                         height=t), dict(x=x, y=y, width=t, height=height), dict(x=x + width - t, y=y, width=t,
                         height=height))):
            tkinter.Place.place_configure(f, **kw)

    def lift(self):
        for f in self.lines:
            f.lift()

    def destroy(self):
        for f in self.lines:
            f.destroy()

def _ghost(app):
    return _Ghost(app.dash)

def _place(w, **kw):
    """Plain Tk place (pixels): customtkinter's place() refuses width / height."""
    w.put(**kw) if isinstance(w, _Ghost) else tkinter.Place.place_configure(w, **kw)

def _unit(app):
    """Row height in screen pixels (follows Windows display scaling)."""
    try:
        return UNIT * ctk.ScalingTracker.get_widget_scaling(app)
    except Exception:
        return UNIT

def _edit_handles(app, cell, card, wid):
    """Edit mode: × on the top-right corner (like the iPad / Mac multitasking close button) and a resize handle."""
    close = ctk.CTkLabel(cell, text="×", width=24, height=24, corner_radius=12, font=F(16, "bold"),
                         fg_color="#5b6577", text_color="#ffffff", cursor="hand2")
    close.place(relx=1, x=-2, y=0, anchor="ne")
    close.bind("<Button-1>", lambda e: _remove(app, wid))
    app.tip(close, t("Remove this widget"))
    grip = ctk.CTkLabel(card, text="◢", font=F(16), text_color=ACCENT, cursor="bottom_right_corner", width=22, height=22)
    grip.place(relx=1, rely=1, x=-4, y=-2, anchor="se")
    st = {}
    def target(e):
        b = _boxes(app)[wid]
        colw = max(1, app.dash.winfo_width() / COLS)
        w = round((st["w"] + e.x_root - st["x"]) / colw)
        h = round((st["h"] + e.y_root - st["y"]) / _unit(app))
        return max(1, min(COLS - b["x"], w)), max(1, min(8, h)), b, colw
    def press(e):
        st.update(x=e.x_root, y=e.y_root, w=cell.winfo_width(), h=cell.winfo_height(), ghost=_ghost(app))
        motion(e)
    def motion(e):
        if "ghost" in st:
            w, h, b, colw = target(e)
            u = _unit(app)
            _place(st["ghost"], x=int(b["x"] * colw), y=int(b["y"] * u), width=int(w * colw), height=int(h * u))
            st["ghost"].lift()
    def release(e):
        if "ghost" in st:
            w, h, _, _ = target(e)
            st.pop("ghost").destroy()
            _save_box(app, wid, w=w, h=h)
    grip.bind("<ButtonPress-1>", press)
    grip.bind("<B1-Motion>", motion)
    grip.bind("<ButtonRelease-1>", release)
    app.tip(grip, t("Drag to resize."))

def _draggable(app, handle, wid):
    """Edit mode: drag a widget by its title to any place on the grid; the others move out of the way.
    Holding the mouse on a title for 0.6 s turns edit mode on (like iOS)."""
    st = {"job": None}
    def press(e):
        if app.widget_edit:
            b = _boxes(app)[wid]
            colw = max(1, app.dash.winfo_width() / COLS)
            st.update(dx=int((e.x_root - app.dash.winfo_rootx()) // colw) - b["x"],
                      dy=int((e.y_root - app.dash.winfo_rooty()) // _unit(app)) - b["y"], ghost=_ghost(app))
            handle.configure(cursor="fleur")
            motion(e)
        else:
            st["job"] = handle.after(600, lambda: _set_edit(app, True))
    def spot(e):
        b = _boxes(app)[wid]
        colw = max(1, app.dash.winfo_width() / COLS)
        x = int((e.x_root - app.dash.winfo_rootx()) // colw) - st["dx"]
        y = int((e.y_root - app.dash.winfo_rooty()) // _unit(app)) - st["dy"]
        return max(0, min(COLS - b["w"], x)), max(0, y), b, colw
    def motion(e):
        if st.get("ghost"):
            x, y, b, colw = spot(e)
            u = _unit(app)
            _place(st["ghost"], x=int(x * colw), y=int(y * u), width=int(b["w"] * colw), height=int(b["h"] * u))
            st["ghost"].lift()
    def release(e):
        if st["job"]:
            handle.after_cancel(st["job"])
            st["job"] = None
        if st.get("ghost"):
            x, y, _, _ = spot(e)
            st.pop("ghost").destroy()
            handle.configure(cursor="")
            _save_box(app, wid, x=x, y=y)
    def menu(e):
        import tkinter
        m = tkinter.Menu(handle, tearoff=0)
        for label, w in ((t("Small"), 1), (t("Wide"), 2), (t("Large"), COLS)):
            m.add_command(label=label, command=lambda w=w: _save_box(app, wid, w=w))
        m.add_separator()
        m.add_command(label=t("Edit widgets"), command=lambda: _set_edit(app, True))
        m.add_command(label=t("Remove"), command=lambda: _remove(app, wid))
        m.tk_popup(e.x_root, e.y_root)
    for w in [handle] + handle.winfo_children():
        w.bind("<ButtonPress-1>", press, add="+")
        w.bind("<B1-Motion>", motion, add="+")
        w.bind("<ButtonRelease-1>", release, add="+")
        w.bind("<Button-3>", menu, add="+")

def _add(app, title):
    wid = next((w for w in _all() if _title(w) == title), None)
    if not wid or wid in _ids(app):
        return _render(app)
    def add(_=None):
        _ids(app).append(wid)
        app.save()
        _render(app)
    if wid in addons.CATALOG and not addons.installed(wid):
        if not app.ask(t("Add widget"), t("This widget is downloaded from the project's GitHub page and checked "
                       "against a fingerprint built into this app. Download it?")):
            return _render(app)
        app.add_menu.set(t("Downloading..."))
        app.bg(lambda: addons.download(wid), add, lambda m: (app.info(t("Add widget"),
               t("Download failed: {e}", e=m)), _render(app)))
        return
    add()

def _remove(app, wid):
    if wid in _ids(app):
        _ids(app).remove(wid)
    app.cfg.get("widget_sizes", {}).pop(wid, None)
    app.save()
    _render(app)

# ---------- game install locations ----------
def games_widget(app, body):
    top = app.row(body)
    lbl = app.label(top, t("Steam games are found automatically. Add other game folders yourself."), 12, muted=True)
    lbl.pack(side="left")
    cols = [("name", t("Game")), ("source", t("Source")), ("drive", t("Drive")), ("kind", t("Drive type")),
            ("size", t("Size (GB)")), ("free", t("Free (GB)")), ("path", t("Path"))]
    tree = app.table(body, cols, (190, 80, 70, 100, 80, 100, 300), 7,
                     {"HDD": WARN, "USB": WARN, "SSD": ACCENT, "NVMe SSD": ACCENT, "Unknown": MUTED})
    note = app.label(body, "", 12, muted=True, wrap=820)
    note.pack(anchor="w", pady=(6, 0))
    def fill(gs):
        if not tree.winfo_exists():
            return
        tree.delete(*tree.get_children())
        for g in gs:
            tree.insert("", "end", iid=g["path"], tags=(g["kind"],),
                        values=(g["name"], t(g["source"]), g["drive"], t(g["kind"]), g["size_gb"] or "-",
                                g["free_gb"] if g["free_gb"] is not None else "-", g["path"]))
        hdd = sum(g["kind"] == "HDD" for g in gs)
        note.configure(text=t("{n} game(s) found.", n=len(gs)) + (" " + t(
            "{n} on a hard drive: they load faster from an SSD. Steam can move a game to another drive "
            "without downloading it again (Steam storage settings or the game's Properties).", n=hdd) if hdd else ""))
    def refresh():
        note.configure(text=t("Scanning..."))
        app.bg(lambda: games.scan(app.cfg.get("manual_games", [])), fill)
    def add():
        if p := filedialog.askdirectory(title=t("Choose a game folder")):
            app.cfg.setdefault("manual_games", []).append(os.path.normpath(p))
            app.save()
            refresh()
    def remove():
        manual = app.cfg.get("manual_games", [])
        for iid in tree.selection():
            if iid in manual:
                manual.remove(iid)
        app.save()
        refresh()
    def open_():
        for iid in tree.selection()[:1]:
            os.startfile(iid)
    tree.bind("<Double-1>", lambda e: open_())
    app.button(top, t("Refresh"), refresh).pack(side="right")
    app.button(top, t("Add folder"), add, primary=False).pack(side="right", padx=6)
    app.button(top, t("Remove"), remove, primary=False).pack(side="right")
    refresh()

# ---------- FPS test ----------
def fps_widget(app, body):
    app.label(body, t("Measures real FPS with Intel PresentMon. Run it once before and once after changing a "
                      "setting, in the same place in the same game, to see whether it helped."), 12, muted=True,
              wrap=820).pack(anchor="w")
    if not bench.presentmon_path():
        r = app.row(body, 8)
        app.label(r, t("PresentMon was not found in the tools folder."), 13).pack(side="left")
        app.button(r, t("Download PresentMon"), lambda: webbrowser.open(PRESENTMON_URL), primary=False).pack(side="right")
    r = app.row(body, (8, 0))
    history = sorted({x["game"] for x in app.cfg.get("bench", [])})
    proc = ctk.CTkComboBox(r, values=history or [""], width=200, height=34, font=F(13), dropdown_font=F(13))
    proc.set(history[0] if history else "")
    proc.pack(side="left")
    secs = app.seg(r, ["30s", "60s", "120s"])
    secs.set("60s")
    secs.pack(side="left", padx=8)
    lab = ctk.CTkEntry(r, placeholder_text=t("Label (e.g. Before)"), width=170, height=34, font=F(13))
    lab.pack(side="left")
    status = app.label(body, t("Type the game's .exe name, start the game, then press Start."), 12, muted=True)
    status.pack(anchor="w", pady=(6, 0))
    tree = app.table(body, [("label", t("Label")), ("game", t("Game")), ("avg", t("Average FPS")),
                            ("low", t("1% low FPS")), ("frames", t("Frames")), ("time", t("Time"))],
                     (140, 170, 100, 100, 80, 120), 5)
    def fill():
        tree.delete(*tree.get_children())
        for i, x in enumerate(app.cfg.get("bench", [])):
            tree.insert("", "end", iid=str(i), values=(x["label"], x["game"], x["avg_fps"], x["low1_fps"],
                                                        x["frames"], x["time"]))
    def done(name, label, res, err):
        btn.configure(state="normal")
        if not status.winfo_exists():
            return
        if err:
            status.configure(text=err, text_color=WARN)
            return
        runs = app.cfg.setdefault("bench", [])
        prev = next((x for x in runs if x["game"].lower() == name.lower()), None)
        runs.insert(0, {"label": label, "game": name, "time": f"{datetime.now():%m-%d %H:%M}", **res})
        del runs[20:]
        app.save()
        fill()
        msg = t("{avg} FPS average, {low} FPS 1% low", avg=res["avg_fps"], low=res["low1_fps"])
        if prev:
            msg += "  " + t("({d:+.1f}% vs '{label}')", d=(res["avg_fps"] / prev["avg_fps"] - 1) * 100, label=prev["label"])
        status.configure(text=msg, text_color=ACCENT)
    def countdown(name, s, label, n):
        if not status.winfo_exists():
            return
        if n:
            status.configure(text=t("Switch to the game. Recording starts in {n} s.", n=n), text_color=WARN)
            app.after(1000, lambda: countdown(name, s, label, n - 1))
            return
        status.configure(text=t("Recording for {s} s...", s=s), text_color=ACCENT)
        def work():
            try:
                res = bench.capture(name, s)
                app.ui(lambda: done(name, label, res, None))
            except Exception as e:
                msg = str(e)
                app.ui(lambda: done(name, label, None, msg))
        threading.Thread(target=work, daemon=True).start()
    def start():
        name = proc.get().strip()
        if not name:
            return
        if not name.lower().endswith(".exe"):
            name += ".exe"
        label = lab.get().strip() or t("Run {n}", n=len(app.cfg.get("bench", [])) + 1)
        btn.configure(state="disabled")
        countdown(name, int(secs.get().rstrip("s")), label, 5)
    def clear():
        app.cfg["bench"] = []
        app.save()
        fill()
    btn = app.button(r, t("Start"), start, width=90)
    btn.pack(side="left", padx=8)
    app.button(r, t("Clear"), clear, primary=False, width=70).pack(side="left")
    fill()

# ---------- memory ----------
def memory_widget(app, body):
    lbl = app.label(body, "", 13)
    lbl.pack(anchor="w")
    tree = app.table(body, [("name", t("App")), ("mb", t("Memory (MB)")), ("n", t("Processes"))], (300, 120, 100), 6)
    def tick():
        s = memory.stats()
        lbl.configure(text=t("In use {used} GB of {total} GB, standby cache {sb} GB", used=s["used"], total=s["total"],
                             sb=s["standby"] or "-"))
        tree.delete(*tree.get_children())
        for a in app.cached("top_apps", lambda: memory.top_apps(6), []):
            tree.insert("", "end", values=(a["name"], a["mb"], len(a["pids"])))
    app.every(3000, tick, tree, "Dashboard")

# ---------- graphics cards ----------
def gpu_widget(app, body):
    tree = app.table(body, [("name", t("Graphics card")), ("vendor", t("Vendor")), ("util", t("Usage")),
                            ("vram", t("VRAM used / total")), ("temp", t("Temperature")), ("fan", t("Fan"))],
                     (280, 80, 70, 140, 100, 90), 3)
    try:
        usage = gpuinfo.Usage()
    except Exception:
        usage = None
    def tick():
        tree.delete(*tree.get_children())
        for g in app.cached(("gpu", id(usage)), lambda: gpuinfo.snapshot(usage), []):
            tree.insert("", "end", values=(g["name"], g["vendor"], f"{g['util']:.0f}%" if g["util"] is not None else "-",
                                           f"{g['vram_used_gb'] if g['vram_used_gb'] is not None else '-'} / {g['vram_gb']} GB",
                                           f"{g['temp']:.0f}°C" if g["temp"] else "-",
                                           f"{g['fan']} RPM" if g["fan"] else "-"))
    app.every(2000, tick, tree, "Dashboard")

WIDGETS = {  # id: (title, builder, default size)
    "clock": ("Clock & calendar", wx.clock_widget, "s"), "network": ("Network", wx.network_widget, "m"),
    "ssd": ("Drive speed", wx.ssd_widget, "m"), "space": ("Free space", wx.space_widget, "m"),
    "battery": ("Battery", wx.battery_widget, "m"), "games": ("Game install locations", games_widget, "l"),
    "fps": ("FPS test", fps_widget, "l"), "memory": ("Top memory users", memory_widget, "m"),
    "gpu": ("Graphics cards", gpu_widget, "l")}
