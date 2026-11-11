"""App management page: autopilot, every installed app (icons, size, grouped by drive or source; right-click to
run, boost, move to another drive or uninstall), boost list."""
import os, subprocess, tkinter as tk
from datetime import datetime
import customtkinter as ctk
from core import appmove, appsdb, boost, gpu, procs
from core.auto import DEFAULT_EXCEPTIONS, RUN_MODES
from core.i18n import t
from .cores import ask_cores
from .theme import ACCENT, BG, CARD2, HOVER2, MUTED, ON_ACCENT, TEXT, WARN, F

def page(app, p):
    profiles = app.cfg.setdefault("boost", [])
    topo = procs.topology()
    _autopilot_card(app, p)

    # ---- every app ----
    body = app.card(p, t("Apps on this PC"), t("Every installed app and game, grouped by where it is installed. "
                    "The list scrolls on its own. Right-click an app to run it, boost it, mark it as a game, move "
                    "it to another drive or uninstall it."))
    top = app.row(body)
    filt = app.seg(top, [t("All"), t("Games"), t("Apps")])
    filt.set(t("All"))
    filt.pack(side="left")
    groups = {t("By drive"): "drive", t("By source"): "source", t("No groups"): None}
    grp = app.seg(top, list(groups))
    grp.set(t("By drive"))
    grp.pack(side="left", padx=8)
    q = ctk.CTkEntry(top, placeholder_text=t("Filter by name"), width=200, height=32, corner_radius=8)
    q.pack(side="left")
    count = app.label(top, t("Indexing installed apps..."), 12, muted=True)
    count.pack(side="right")
    tree = app.table(body, [("kind", t("Type")), ("size", t("Size")), ("gpu", t("Graphics")), ("source", t("Source")),
                            ("path", t("Path"))], (80, 90, 110, 120, 330), 16)
    tree.configure(show="tree headings")
    tree.heading("#0", text=t("Name"), anchor="w")
    tree.column("#0", width=300, anchor="w")
    tree.tag_configure("group", foreground=ACCENT)
    images = app.__dict__.setdefault("_icons", {})
    state = {"apps": [], "sizing": False}
    def is_game(a):
        mark = app.cfg.get("game_marks", {}).get((a["exe"] or a["name"]).lower())
        return a["game"] if mark is None else mark
    def gpu_text(prefs, a):
        """The Windows graphics preference of the app (Settings > Display > Graphics), '-' if none is set."""
        v = prefs.get((a["exe"] or "").lower(), "")
        level = next((n for n, lv in gpu.PREFS.items() if f"GpuPreference={lv};" in v), None)
        return t(level) if level and level != "Let Windows decide" else "-"
    def set_gpu(level):
        a = chosen()
        if not a or not a["exe"]:
            return app.info(t("Graphics"), t("The program file of this app is unknown, so its graphics card cannot "
                                             "be chosen. Use Graphics & Games > Per-app graphics card instead."))
        try:
            gpu.set_app_pref(a["exe"], gpu.PREFS[level])
        except OSError as e:
            return app.info(t("Graphics"), str(e))
        fill()
        app.info(t("Graphics"), t("{name}: {level}. Restart the app if it is running.", name=a["name"], level=t(level)))
    def size_text(mb):
        return "-" if not mb else f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb} MB"
    sort = {"col": "#0", "desc": False}
    heads = {"#0": t("Name"), "kind": t("Type"), "size": t("Size"), "gpu": t("Graphics"), "source": t("Source")}
    def kind(a):
        exe = os.path.basename(a["exe"] or "").lower()
        if any(x.get("ai") and x.get("exe", "").lower() == exe for x in app.cfg.get("boost", [])):
            return t("AI app")
        return t("Game") if is_game(a) else t("App")
    def sort_key(item):
        i, a = item
        col = sort["col"]
        if col == "size":
            return a.get("size_mb") or 0
        if col == "kind":
            return (kind(a), a["name"].lower())
        if col == "gpu":
            return (gpu_text(prefs_now(), a), a["name"].lower())
        if col == "source":
            return (t(a.get("source") or "Other"), a["name"].lower())
        return a["name"].lower()
    def prefs_now():
        return sort.get("prefs", {})
    def sort_by(col):
        sort["desc"] = not sort["desc"] if sort["col"] == col else col == "size"  # sizes start with the largest
        sort["col"] = col
        for c, label in heads.items():
            tree.heading(c, text=label + ((" ▼" if sort["desc"] else " ▲") if c == col else ""))
        fill()
    for c in heads:
        tree.heading(c, command=lambda c=c: sort_by(c))
    app.tip(tree, t("Click a column title (name, type, size, source) to sort; click again to reverse."))
    def fill(*_):
        tree.delete(*tree.get_children())
        f, text, key = filt.get(), q.get().lower().strip(), groups[grp.get()]
        shown, parents = 0, {}
        try:
            prefs = {k.lower(): v for k, v in gpu.list_app_prefs().items()}
        except Exception:
            prefs = {}
        sort["prefs"] = prefs
        items = sorted(enumerate(state["apps"]), key=sort_key, reverse=sort["desc"])
        if key:  # groups follow the same order (by total size when sorting by size)
            totals = {}
            for _, a in items:
                label = (a.get(key) or "-") if key == "drive" else t(a.get(key) or "Other")
                totals[label] = totals.get(label, 0) + (a.get("size_mb") or 0)
            for label in sorted(totals, key=lambda l: totals[l] if sort["col"] == "size" else l, reverse=sort["desc"]):
                parents[label] = [tree.insert("", "end", text=label, open=True, tags=("group",)), 0]
        for i, a in items:
            g = is_game(a)
            if (f == t("Games") and not g) or (f == t("Apps") and g) or (text and text not in a["name"].lower()):
                continue
            parent = ""
            if key:
                label = (a.get(key) or "-") if key == "drive" else t(a.get(key) or "Other")
                if label not in parents:
                    parents[label] = [tree.insert("", "end", text=label, open=True, tags=("group",)), 0]
                parents[label][1] += a.get("size_mb") or 0
                parent = parents[label][0]
            tree.insert(parent, "end", iid=str(i), text="  " + a["name"], image=images.get(i, ""),
                        values=(kind(a), size_text(a.get("size_mb")), gpu_text(prefs, a), t(a.get("source") or "Other"),
                                a.get("folder") or a["exe"] or ""))
            shown += 1
        for label, (iid, mb) in parents.items():
            if mb or tree.get_children(iid):
                tree.item(iid, values=("", size_text(mb), "", "", ""))
            else:
                tree.delete(iid)  # filtered out completely
        count.configure(text=t("{n} apps", n=shown))
    def got_icons(pil):
        from PIL import ImageTk
        for i, im in pil.items():
            images[i] = ImageTk.PhotoImage(im.resize((20, 20)))
            if tree.exists(str(i)):
                tree.item(str(i), image=images[i])
    def got_sizes(sizes):
        for i, mb in sizes.items():
            state["apps"][i]["size_mb"] = mb
        __import__("core.appsdb", fromlist=["save_cache"]).save_cache(state["apps"])
        fill()
    def got_apps(apps):
        state["apps"] = apps
        app.app_index = apps
        fill()
        def load_icons():
            from core import icons
            out = {}
            for i, a in enumerate(apps):
                try:
                    im = icons.icon(a["icon"])
                    if im:
                        out[i] = im
                except Exception:
                    pass
            return out
        def sizes():  # apps whose installer did not record a size
            return {i: appsdb.folder_size_mb(a["folder"]) for i, a in enumerate(apps)
                    if not a.get("size_mb") and a.get("folder") and os.path.isdir(a["folder"])}
        app.bg(load_icons, got_icons, lambda m: None)
        app.bg(sizes, got_sizes, lambda m: None)
    filt.configure(command=fill)
    grp.configure(command=fill)
    q.bind("<KeyRelease>", fill)
    if app.app_index:  # cached list from the last start: show it at once
        got_apps(app.app_index)
    app.bg(appsdb.scan, got_apps, lambda m: count.configure(text=m))

    def chosen():
        sel = tree.selection()
        return state["apps"][int(sel[0])] if sel and sel[0].isdigit() else None
    def add_profile(ai=False):
        a = chosen()
        if a and a["exe"] and not any(x["exe"] == os.path.basename(a["exe"]).lower() for x in profiles):
            prof = boost.new_profile(a["name"], a["exe"], ai)
            prof["game"] = is_game(a)
            profiles.append(prof)
            app.save()
            fill_profiles()
    def mark(game):
        a = chosen()
        if a:
            app.cfg.setdefault("game_marks", {})[(a["exe"] or a["name"]).lower()] = game
            app.save()
            app.refresh_games()
            fill()
    def uninstall():
        a = chosen()
        if a and app.ask(t("Uninstall"), t("Uninstall {pid}?", pid=a["name"]), warn=True):
            try:
                appsdb.uninstall(a)
            except Exception:
                app.info(a["name"], t("This app has no uninstaller."))
    def move():
        a = chosen()
        if a:
            move_dialog(app, a, lambda: app.bg(appsdb.scan, got_apps, lambda m: None))
    def locate():
        a = chosen()
        target = a and (a["exe"] if a["exe"] and os.path.exists(a["exe"]) else a.get("folder"))
        if target:
            subprocess.Popen(["explorer", "/select,", target] if os.path.isfile(target) else ["explorer", target])
    menu = tk.Menu(tree, tearoff=0, bg=CARD2, fg=TEXT, activebackground=HOVER2, activeforeground=TEXT, bd=0,
                   font=(F(12).cget("family"), 10))
    menu.add_command(label=t("Run"), command=lambda: chosen() and chosen()["exe"] and appsdb.run(chosen()))
    menu.add_command(label=t("Add to boost list"), command=add_profile)
    menu.add_command(label=t("Add as AI app"), command=lambda: add_profile(True))
    menu.add_separator()
    menu.add_command(label=t("Mark as game"), command=lambda: mark(True))
    menu.add_command(label=t("Mark as app (not a game)"), command=lambda: mark(False))
    gmenu = tk.Menu(menu, tearoff=0, bg=CARD2, fg=TEXT, activebackground=HOVER2, activeforeground=TEXT, bd=0,
                    font=(F(12).cget("family"), 10))
    for level in ("High performance", "Power saving", "Let Windows decide"):
        gmenu.add_command(label=t(level), command=lambda lv=level: set_gpu(lv))
    menu.add_cascade(label=t("Graphics card"), menu=gmenu)
    menu.add_command(label=t("Open file location"), command=locate)
    menu.add_command(label=t("Move to another drive..."), command=move)
    menu.add_separator()
    menu.add_command(label=t("Uninstall"), command=uninstall)
    def popup(e):
        iid = tree.identify_row(e.y)
        if iid and iid.isdigit():
            tree.selection_set(iid)
            menu.tk_popup(e.x_root, e.y_root)
    tree.bind("<Button-3>", popup)
    tree.bind("<Double-1>", lambda e: chosen() and chosen()["exe"] and appsdb.run(chosen()))

    # ---- boost list ----
    body = app.card(p, t("Boost list"), t("Apps that get their own priority and CPU cores every time they start. "
                                          "Games in this list also turn on maximum performance."))
    ptree = app.table(body, [("name", t("Name")), ("pri", t("Priority")), ("cores", t("Cores")), ("kind", t("Type")),
                             ("power", t("Power mode while running"))], (240, 120, 130, 100, 200), 5)
    def cores_text(c):
        return t("Auto") if c == "auto" else t("All") if c == "all" else ",".join(map(str, c))
    def fill_profiles():
        ptree.delete(*ptree.get_children())
        for i, x in enumerate(profiles):
            kind = t("AI app") if x.get("ai") else t("Game") if x.get("game") else t("App")
            power = t(x.get("power") or "Ultimate") if x.get("plan", True) else t("No change")
            ptree.insert("", "end", iid=str(i), values=(x["name"], t(x["priority"]), cores_text(x["cores"]), kind, power))
    def sel():
        return [profiles[int(i)] for i in ptree.selection()]
    def edit(key, val):
        for x in sel():
            x[key] = val
        app.save()
        fill_profiles()
    def remove():
        for x in sel():
            profiles.remove(x)
        app.save()
        fill_profiles()
    adv = app.details(body)
    r = app.row(adv)
    pri = ctk.CTkOptionMenu(r, values=[t(k) for k in procs.PRIORITIES], width=140, height=32, fg_color=CARD2,
                            button_color=CARD2, button_hover_color=HOVER2,
                            command=lambda v: edit("priority", next(k for k in procs.PRIORITIES if t(k) == v)))
    pri.set(t("Priority"))
    pri.pack(side="left")
    modes = {t(m): m for m in RUN_MODES + ["No change"]}
    def set_power(v):
        for x in sel():
            x["plan"] = modes[v] != "No change"
            x["power"] = modes[v] if x["plan"] else None
        app.save()
        fill_profiles()
    pm = ctk.CTkOptionMenu(r, values=list(modes), width=170, height=32, fg_color=CARD2, button_color=CARD2,
                           button_hover_color=HOVER2, command=set_power)
    pm.set(t("Power mode"))
    pm.pack(side="left", padx=(6, 0))
    app.tip(pm, t("Power mode while the selected apps run. With several listed apps open, the strongest one wins."))
    app.button(r, t("Cores..."), lambda: sel() and ask_cores(app, topo, lambda cs: edit("cores", cs)),
               primary=False, width=100).pack(side="left", padx=6)
    app.button(r, t("Remove"), remove, primary=False, width=90).pack(side="left")
    fill_profiles()

    # ---- background picture of this app ----
    from .pages import background_card
    background_card(app, p)

def _autopilot_card(app, p):
    c = app.cfg
    body = app.card(p, t("Auto optimize"), t("Games run at maximum performance and the PC goes back to the mode below "
                    "when they close. Apps you are not using are put into efficiency mode so the app in front gets "
                    "the CPU, and they return to normal as soon as you switch to them."))
    def toggle(on):
        c["autopilot"] = on
        app.save()
        app.set_autopilot(on)
    app.switch_row(body, t("Auto optimize"), "", c.get("autopilot", True), toggle)
    adv = app.details(body)
    power_rows(app, adv)
    r = app.row(adv, 4)
    app.label(r, t("Games not in the boost list"), 13).pack(side="left")
    gnames = [t(m) for m in RUN_MODES]
    gseg = app.seg(r, gnames, lambda v: (c.__setitem__("game_power", RUN_MODES[gnames.index(v)]), app.save()))
    gseg.set(t(c.get("game_power", "Ultimate")))
    gseg.pack(side="right")
    app.switch_row(adv, t("Slow down apps in the background"), t("Efficiency mode for apps that are not in front."),
                   c.get("throttle", True), lambda on: (c.__setitem__("throttle", on), app.save()))
    app.switch_row(adv, t("Also move them to efficiency cores"), t("Intel hybrid CPUs only."),
                   c.get("ecores", False), lambda on: (c.__setitem__("ecores", on), app.save()))
    app.switch_row(adv, t("While gaming: lower background app priority"), t("Background apps get less CPU time "
                   "while a game runs and return to normal afterwards."), c.get("game_priority", True),
                   lambda on: (c.__setitem__("game_priority", on), app.save()))
    app.switch_row(adv, t("While gaming: free RAM when the game starts"), t("Moves idle memory of background apps "
                   "out of RAM. Useful with 8-16 GB; those apps react slower the first time you switch back."),
                   c.get("game_trim", False), lambda on: (c.__setitem__("game_trim", on), app.save()))
    app.label(adv, t("Never slow down these apps (comma separated):"), 13).pack(anchor="w", pady=(6, 2))
    ex = ctk.CTkEntry(adv, height=32)
    ex.insert(0, ", ".join(c.get("exceptions", DEFAULT_EXCEPTIONS)))
    ex.pack(fill="x")
    ex.bind("<FocusOut>", lambda e: (c.__setitem__("exceptions", [x.strip().lower() for x in ex.get().split(",")
                                                                    if x.strip()]), app.save()))
    app.autopilot_log = app.console(adv, 120)
    for line in getattr(app, "autopilot_lines", []):
        app.write(app.autopilot_log, line)

def move_dialog(app, a, done):
    """Pick a target drive; Steam and Store apps are sent to their own move feature."""
    import psutil
    if a.get("source") == "Steam":
        if app.ask(t("Move to another drive..."), t("Steam moves games itself without downloading them again: Steam > "
                   "Settings > Storage, pick the game, then Move. Open Steam settings now?")):
            appmove.open_steam_storage()
        return
    if a.get("source") == "Microsoft Store":
        appmove.open_store_move()
        return
    if not a.get("folder") or not os.path.isdir(a["folder"]):
        return app.info(a["name"], t("The install folder of this app is unknown, so it cannot be moved."))
    here = a["folder"][:2].upper()
    drives = [p.device[:2] for p in psutil.disk_partitions() if p.fstype == "NTFS" and p.device[:2].upper() != here]
    if not drives:
        return app.info(a["name"], t("No other NTFS drive found."))
    win = ctk.CTkToplevel(app, fg_color=BG)
    win.title(t("Move to another drive..."))
    win.transient(app)
    win.grab_set()
    app.label(win, t("{name} ({size}) will be copied to the chosen drive and a link is left in the old place, so "
                     "shortcuts and the uninstaller keep working. Close the app first. Apps with anti-cheat or their "
                     "own drivers may not work after moving.", name=a["name"],
                     size=f"{(a.get('size_mb') or 0) / 1024:.1f} GB"), 13, wrap=440).pack(padx=16, pady=(14, 8))
    seg = app.seg(win, [f"{d}  ({psutil.disk_usage(d + chr(92)).free / 2**30:.0f} GB {t('free')})" for d in drives])
    seg.set(seg.cget("values")[0])
    seg.pack(padx=16, pady=6)
    status = app.label(win, "", 12, muted=True, wrap=440)
    status.pack(padx=16)
    def go():
        dest = seg.get()[:2] + "\\"
        btn.configure(state="disabled")
        status.configure(text=t("Copying... this can take several minutes."))
        def ok(path):
            status.configure(text=t("Moved to {p}", p=path))
            done()
        def fail(msg):
            btn.configure(state="normal")
            status.configure(text=t("Not moved: {e}", e=msg), text_color=WARN)
        app.bg(lambda: appmove.move(a["folder"], dest), ok, fail)
    btn = app.button(win, t("Move"), go)
    btn.pack(padx=16, pady=(8, 14), anchor="e")

POWER_MODES = ["Best performance", "Balanced", "Best power efficiency"]

def power_rows(app, parent, on_change=None):
    """Power mode outside games, separately for charger and battery (battery only on laptops)."""
    import psutil
    c = app.cfg
    box = ctk.CTkFrame(parent, fg_color="transparent", height=1)
    def only(on):
        c["power_only_listed"] = on
        app.save()
        box.pack_forget() if on else box.pack(fill="x", after=sw.master)
        if on_change:
            on_change()
    sw = app.switch_row(parent, t("Change the power mode only while a listed app runs"), t(
        "On: maximum performance only while a game or an app in the boost list runs; afterwards the power mode you "
        "had before comes back, and nothing changes the rest of the time. Off: also switch modes when the charger is "
        "connected or removed."), c.get("power_only_listed", True), only)
    if not c.get("power_only_listed", True):
        box.pack(fill="x")
    rows = [("power_ac", t("When plugged in (no game running)"))]
    if psutil.sensors_battery():
        rows.append(("power_dc", t("On battery (no game running)")))
    for key, label in rows:
        r = app.row(box, 4)
        app.label(r, label, 13).pack(side="left")
        names = [t(m) for m in POWER_MODES]
        def pick(v, key=key):
            c[key] = POWER_MODES[names.index(v)]
            app.save()
            if on_change:
                on_change()
        seg = app.seg(r, names, pick)
        seg.set(t(c.get(key) or c.get("idle_mode", "Balanced")))
        seg.pack(side="right")
        app.tip(r, t("Switches the Windows power mode automatically when the charger is connected or removed. "
                     "While a game runs, Auto optimize uses maximum performance."))
    if psutil.sensors_battery():
        app.switch_row(parent, t("Maximum performance for games on battery"), t("Off keeps the battery mode while "
                       "gaming on battery: longer battery life, lower FPS. The laptop limits power on battery anyway."),
                       c.get("battery_game_max", True), lambda on: (c.__setitem__("battery_game_max", on), app.save()))
