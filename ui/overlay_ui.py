"""Overlay page: turn the overlay and each item on or off (tiles), position, look and presets."""
import copy
import customtkinter as ctk
from core.i18n import t
from . import overlay as ov
from .theme import ACCENT, BORDER, CARD2, HOVER2, MUTED, ON_ACCENT, TEXT, WARN, F, IF, icon

ARROWS = {"tl": "↖", "tc": "↑", "tr": "↗", "bl": "↙", "br": "↘"}

def page(app, p):
    c = ov.cfg_of(app)
    body = app.card(p, t("Overlay"), t("Shows FPS, temperatures, clocks and more on top of games. Works in windowed and "
                    "borderless (full-screen windowed) mode; exclusive full-screen games may draw over it. Nothing is "
                    "injected into the game, so anti-cheat is not touched."))
    def toggle(on):
        c["on"] = on
        app.save()
        app.start_overlay() if on else app.overlay.hide()
    app.switch_row(body, t("Show overlay"), t("{k} turns it on and off in any app.", k=c["hotkey"]),
                   c["on"], toggle, glyph="overlay")
    app.switch_row(body, t("Turn on automatically when a game starts"), "", c["auto"],
                   lambda on: (c.__setitem__("auto", on), app.save()), glyph="game")
    app.switch_row(body, t("Only measure games"), t("Off: measures whatever app is in front, not only games."),
                   c["games_only"], lambda on: (c.__setitem__("games_only", on), app.save()), glyph="speed")
    app.label(body, t("Use borderless / full-screen windowed mode in the game's settings so the overlay stays visible."),
              11, muted=True, wrap=820).pack(anchor="w", pady=(4, 0))
    _shortcut(app, body, c)
    _tiles(app, p, c)
    _position(app, p, c)
    _presets(app, p, c)

def _shortcut(app, body, c):
    """Click the button, then press the keys (for example Ctrl+Alt+F)."""
    r = app.row(body, (8, 0))
    app.label(r, t("Shortcut to turn the overlay on and off"), 13).pack(side="left")
    status = app.label(body, "", 12, muted=True)
    status.pack(anchor="w")
    def record():
        btn.configure(text=t("Press the keys..."))
        top = app.winfo_toplevel()
        def key(e):
            name = e.keysym
            if name in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Win_L", "Win_R",
                        "Meta_L", "Meta_R"):
                return "break"  # wait for the main key
            if name == "Escape":
                return done(None)
            mods = [m for m, bit in (("Ctrl", 0x4), ("Shift", 0x1), ("Alt", 0x20000)) if e.state & bit]
            key_name = {"Prior": "PageUp", "Next": "PageDown", "Scroll_Lock": "ScrollLock", "space": "Space"}.get(
                name, name.upper() if len(name) == 1 else name)
            return done("+".join(mods + [key_name]))
        def done(combo):
            top.unbind("<KeyPress>")
            if combo and ov.parse_hotkey(combo):
                c["hotkey"] = combo
                app.save()
                app.restart_hotkey()
                app.after(600, check)
            elif combo:
                status.configure(text=t("{k} cannot be used. Use Ctrl, Alt or Shift with a letter, a number or F1-F12.",
                                        k=combo), text_color=WARN)
            btn.configure(text=c["hotkey"])
            return "break"
        top.bind("<KeyPress>", key)
        top.focus_force()
    def check():
        hk = getattr(app, "hotkey", None)
        if hk is not None and hk.ok is False:
            status.configure(text=t("{k} is already used by another app. Pick another shortcut.", k=c["hotkey"]),
                             text_color=WARN)
        else:
            status.configure(text=t("Saved: {k}", k=c["hotkey"]), text_color=MUTED)
    btn = app.button(r, c["hotkey"], record, primary=False, width=160,
                     tooltip=t("Click, then press the new keys. Esc cancels."))
    btn.pack(side="right")

def _tiles(app, p, c):
    body = app.card(p, t("Items"), t("Turn on only what you want to see. Drag a tile onto another one to change the "
                    "order in the overlay."))
    grid = app.scroll_box(body, 300)
    grid.grid_columnconfigure((0, 1), weight=1, uniform="tile")
    def draw():
        for w in grid.winfo_children():
            w.destroy()
        for i, k in enumerate(c["order"]):
            title, glyph, _, desc = ov.MODULES[k]
            tile = ctk.CTkFrame(grid, fg_color=CARD2, corner_radius=8, border_width=1, border_color=BORDER, height=52)
            tile.grid(row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)
            tile.pack_propagate(False)
            tile.key = k
            ctk.CTkLabel(tile, text=icon(glyph), font=IF(18), text_color=ACCENT if c["modules"][k] else MUTED,
                         width=36).pack(side="left", padx=(10, 6))
            app.label(tile, t(title), 13).pack(side="left")
            sw = ctk.CTkSwitch(tile, text="", progress_color=ACCENT, width=44)
            sw.pack(side="right", padx=10)
            own = k in c["detached"]
            pin = ctk.CTkButton(tile, text="⇱", width=28, height=26, corner_radius=8, font=F(14),
                                fg_color=ACCENT if own else "transparent", hover_color=HOVER2,
                                text_color=ON_ACCENT if own else MUTED, command=lambda k=k: detach(k))
            pin.pack(side="right")
            app.tip(pin, t("Own box: this item gets its own position. Move it with 'Move with the mouse'. "
                           "Click again to put it back in the main box."))
            sw.select() if c["modules"][k] else sw.deselect()
            sw.configure(command=lambda k=k, sw=sw: (c["modules"].__setitem__(k, bool(sw.get())), app.save(), draw()))
            app.tip(tile, t(desc))
            for w in [tile] + tile.winfo_children():
                if not isinstance(w, (ctk.CTkSwitch, ctk.CTkButton)):
                    w.bind("<ButtonRelease-1>", lambda e, k=k: drop(e, k), add="+")
        app.fit_scroll(grid)
    def detach(k):
        if c["detached"].pop(k, None) is None:
            n = len(c["detached"])
            c["detached"][k] = {"x": int(c["x"]) + 260 + 40 * n, "y": int(c["y"]) + 40 * n}
        app.save()
        app.overlay.apply_style()
        draw()
    def drop(e, k):
        target = app.winfo_containing(e.x_root, e.y_root)
        while target is not None and not hasattr(target, "key"):
            target = target.master
        if target is not None and target.key != k:
            c["order"].remove(k)
            c["order"].insert(c["order"].index(target.key), k)
            app.save()
            draw()
    draw()

def _position(app, p, c):
    body = app.card(p, t("Position and look"), t("Default: top left. Pick a corner, type an exact position, or "
                    "move it with the mouse. Items with their own box (the ⇱ button) are moved with the mouse."))
    r = app.row(body)
    app.label(r, t("Position"), 13, width=110, anchor="w").pack(side="left")
    keys = list(ARROWS)
    pos = app.seg(r, [ARROWS[k] for k in keys], lambda v: set_pos(keys[[ARROWS[k] for k in keys].index(v)]))
    pos.set(ARROWS.get(c["pos"], ARROWS["tl"]))
    pos.pack(side="left")
    def set_pos(k):
        c["pos"] = k
        app.save()
        app.overlay.apply_style()
    r2 = app.row(body, (6, 0))
    app.label(r2, t("Exact position (px)"), 13, width=110, anchor="w").pack(side="left")
    xs, ys = (ctk.CTkEntry(r2, width=70, height=30, corner_radius=8) for _ in range(2))
    for e, v in ((xs, c["x"]), (ys, c["y"])):
        e.insert(0, str(v))
    app.label(r2, "X", 12, muted=True).pack(side="left")
    xs.pack(side="left", padx=4)
    app.label(r2, "Y", 12, muted=True).pack(side="left")
    ys.pack(side="left", padx=4)
    def custom():
        try:
            c.update(pos="custom", x=int(xs.get()), y=int(ys.get()))
        except ValueError:
            return
        app.save()
        app.overlay.apply_style()
    app.button(r2, t("Apply"), custom, primary=False, width=70).pack(side="left", padx=6)
    edit = {"on": False}
    def move():
        edit["on"] = not edit["on"]
        app.overlay.set_edit(edit["on"])
        mbtn.configure(text=t("Done") if edit["on"] else t("Move with the mouse"))
        if not edit["on"]:
            xs.delete(0, "end"), xs.insert(0, str(c["x"])), ys.delete(0, "end"), ys.insert(0, str(c["y"]))
    mbtn = app.button(r2, t("Move with the mouse"), move, primary=False)
    mbtn.pack(side="left", padx=6)
    try:
        n = len(ov.monitors())
    except Exception:
        n = 1
    if n > 1:
        r3 = app.row(body, (6, 0))
        app.label(r3, t("Monitor"), 13, width=110, anchor="w").pack(side="left")
        mon = app.seg(r3, [str(i + 1) for i in range(n)], lambda v: (c.__setitem__("monitor", int(v) - 1), app.save(),
                                                                   app.overlay.apply_style()))
        mon.set(str(min(c["monitor"], n - 1) + 1))
        mon.pack(side="left")
    r4 = app.row(body, (6, 0))
    app.label(r4, t("Text size"), 13, width=110, anchor="w").pack(side="left")
    sizes = {t("Small"): "s", t("Medium"): "m", t("Large"): "l"}
    sz = app.seg(r4, list(sizes), lambda v: (c.__setitem__("size", sizes[v]), app.save()))
    sz.set(next(k for k, v in sizes.items() if v == c["size"]))
    sz.pack(side="left")
    r5 = app.row(body, (6, 0))
    app.label(r5, t("Box opacity"), 13, width=110, anchor="w").pack(side="left")
    op = ctk.CTkSlider(r5, from_=0.0, to=1.0, width=220, progress_color=ACCENT, button_color=ACCENT,
                       button_hover_color=ACCENT)
    op.set(c["box"])
    val = app.label(r5, "", 12, muted=True)
    def set_box(v):
        c["box"] = round(v, 2)
        val.configure(text=t("No box (text only)") if c["box"] < 0.03 else f"{c['box'] * 100:.0f}%")
        app.overlay.apply_style()
    op.configure(command=set_box)
    op.bind("<ButtonRelease-1>", lambda e: app.save())
    op.pack(side="left")
    val.pack(side="left", padx=8)
    set_box(c["box"])
    app.tip(r5, t("Only the dark box behind the text changes; the text stays fully visible. All the way left "
                  "removes the box."))
    def reset():
        keep = c.get("presets", {})
        c.clear()
        c.update(ov.default_cfg(), presets=keep, on=bool(app.overlay.win))
        c["detached"] = {}
        app.save()
        app.overlay.apply_style()
        app.info(t("Overlay"), t("Back to the default items and the top-left corner. Open the page again to see it."))
    app.button(app.row(body, (8, 0)), t("Reset to default"), reset, primary=False).pack(side="left")

def _presets(app, p, c):
    body = app.card(p, t("Presets"), t("Save the current items, position and look under a name, e.g. one per game."))
    r = app.row(body)
    name = ctk.CTkEntry(r, width=180, height=30, corner_radius=8, placeholder_text=t("Preset name"))
    name.pack(side="left")
    keep = ("modules", "order", "pos", "x", "y", "monitor", "size", "box", "detached")
    pick = ctk.CTkOptionMenu(r, values=list(c["presets"]) or ["-"], width=160, height=30, corner_radius=8,
                             fg_color=CARD2, button_color=CARD2, button_hover_color=HOVER2, text_color=TEXT)
    def save():
        n = name.get().strip()
        if n:
            c["presets"][n] = copy.deepcopy({k: c[k] for k in keep})
            app.save()
            pick.configure(values=list(c["presets"]))
            pick.set(n)
    def load():
        pr = c["presets"].get(pick.get())
        if pr:
            c.update(copy.deepcopy(pr))
            app.save()
            app.overlay.apply_style()
    def delete():
        if c["presets"].pop(pick.get(), None) is not None:
            app.save()
            pick.configure(values=list(c["presets"]) or ["-"])
            pick.set((list(c["presets"]) or ["-"])[0])
    app.button(r, t("Save"), save, primary=False, width=70).pack(side="left", padx=6)
    pick.pack(side="left", padx=(12, 0))
    pick.set((list(c["presets"]) or ["-"])[0])
    app.button(r, t("Load"), load, primary=False, width=70).pack(side="left", padx=6)
    app.button(r, t("Delete"), delete, primary=False, width=70).pack(side="left")
