"""Page sections."""
import os, webbrowser
from datetime import datetime
from tkinter import filedialog
import customtkinter as ctk
from core import (browsers as br, cleaner, cooling as cool, disk, gpu, gpuinfo, hardware,
                  space, tweaks)
from core.diag import Sampler
from core import lang_ko
from core.i18n import t
from core.version import REPO, __version__
from .theme import ACCENT, CARD2, MUTED, WARN, F


def _tweak_switch(app, body, name, desc):
    def change(on):
        if tweaks.apply(name, on):
            app.info(t("Restart needed"), t("Restart Windows to apply this change."))
    app.switch_row(body, t(name), desc, tweaks.state(name) == "on", change)

# ---------- Graphics ----------
def graphics(app, p):
    body = app.card(p, t("Graphics cards"), t("Works with NVIDIA, AMD Radeon and Intel graphics, integrated and "
                                              "discrete. Temperature and fan speed appear when the driver reports them."))
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
                                           f"{g['temp']:.0f}°C" if g["temp"] else "-", f"{g['fan']} RPM" if g["fan"] else "-"))
    app.every(2000, tick, tree, "Graphics & Games")

    body = app.card(p, t("Windows graphics settings"))
    _tweak_switch(app, body, "HW-accelerated GPU scheduling", t("Lets the GPU manage its own memory scheduling. "
                                                                "Restart required."))
    app.switch_row(body, t("Optimizations for windowed games"), t("DX10/11 games in windowed or borderless mode use "
                   "the flip model: lower latency, Auto HDR and VRR. Restart the game after changing."),
                   gpu.windowed_opt(), gpu.set_windowed_opt)
    app.switch_row(body, t("Variable refresh rate"), t("VRR for DX11 full-screen games that do not support it "
                   "themselves. Needs a G-Sync or FreeSync display."), gpu.global_flag(gpu.VRR),
                   lambda on: gpu.set_global_flag(gpu.VRR, on))

    gpu_apps(app, p)

def gpu_apps(app, p):
    """Per-app graphics card: the installed apps as a list (like App management); pick one or more and a GPU."""
    body = app.card(p, t("Per-app graphics card"), t("Run games on the discrete GPU on laptops with two GPUs. Select "
                    "apps (Ctrl or Shift for several) and press a button below. Restart an app that is running."))
    top = app.row(body)
    filt = app.seg(top, [t("Games"), t("All")])
    filt.set(t("Games"))
    filt.pack(side="left")
    q = ctk.CTkEntry(top, placeholder_text=t("Filter by name"), width=200, height=32, corner_radius=8)
    q.pack(side="left", padx=8)
    tree = app.table(body, [("gpu", t("Graphics card")), ("path", t("Path"))], (150, 430), 10)
    tree.configure(show="tree headings", selectmode="extended")
    tree.heading("#0", text=t("Name"), anchor="w")
    tree.column("#0", width=280, anchor="w")
    icons = app.__dict__.setdefault("_icons", {})
    rows = {}
    def level_of(v):
        return next((n for n, lv in gpu.PREFS.items() if f"GpuPreference={lv};" in (v or "")), "Let Windows decide")
    def fill(*_):
        tree.delete(*tree.get_children())
        rows.clear()
        try:
            prefs = {k.lower(): (k, v) for k, v in gpu.list_app_prefs().items()}
        except Exception:
            prefs = {}
        marks, games, text = app.cfg.get("game_marks", {}), filt.get() == t("Games"), q.get().lower().strip()
        seen = set()
        for i, a in enumerate(app.app_index):
            exe = a.get("exe") or ""
            if not exe or exe.lower() in seen:
                continue
            seen.add(exe.lower())
            g = marks.get(exe.lower(), a.get("game"))
            lv = level_of(prefs.get(exe.lower(), ("", ""))[1])
            if (games and not g and lv == "Let Windows decide") or (text and text not in a["name"].lower()):
                continue
            rows[str(i)] = exe
            tree.insert("", "end", iid=str(i), text="  " + a["name"], image=icons.get(i, ""), values=(
                t(lv) if lv != "Let Windows decide" else "-", exe))
        for low, (path, v) in prefs.items():  # set earlier for a program that is not in the app list
            if low not in seen and (not text or text in low):
                rows["x" + str(len(rows))] = path
                tree.insert("", "end", iid="x" + str(len(rows) - 1), text="  " + os.path.basename(path),
                            values=(t(level_of(v)), path))
    def apply(level):
        for iid in tree.selection():
            gpu.set_app_pref(rows[iid], gpu.PREFS[level])
        fill()
    def add():
        if path := filedialog.askopenfilename(filetypes=[("exe", "*.exe")]):
            gpu.set_app_pref(path.replace("/", "\\"), gpu.PREFS["High performance"])
            fill()
    r = app.row(body, (8, 0))
    for level in ("High performance", "Power saving", "Let Windows decide"):
        app.button(r, t(level), lambda lv=level: apply(lv), primary=level == "High performance").pack(side="left",
                                                                                                    padx=(0, 6))
    app.button(r, t("Other .exe..."), add, primary=False).pack(side="right")
    filt.configure(command=fill)
    q.bind("<KeyRelease>", fill)
    if app.app_index:
        fill()
    else:
        from core import appsdb
        app.bg(appsdb.scan, lambda apps: (setattr(app, "app_index", apps), fill()), lambda m: None)

# ---------- Cooling ----------
def cooling(app, p):
    body = app.card(p, t("Cooling policy"), t("Active: the fan speeds up before the CPU slows down (cooler and "
                    "faster, louder). Passive: the CPU slows down before the fan speeds up (quieter). Applies to the "
                    "current power plan. Some PCs ignore this setting."))
    r = app.row(body)
    pol = app.seg(r, [t("Active"), t("Passive")], lambda v: cool.set_cooling_policy(v == t("Active")))
    pol.pack(side="left")
    try:
        ac, _ = cool.cooling_policy()
        if ac is not None:
            pol.set(t("Active") if ac else t("Passive"))
    except Exception:
        pass

    body = app.card(p, t("Power mode"), t("Same as the power mode in Windows Settings. Best performance lets the CPU "
                                          "and fans run harder; best power efficiency is quieter and cooler."))
    names = list(cool.MODES)
    mode = app.seg(app.row(body), [t(n) for n in names],
                   lambda v: cool.set_power_mode(names[[t(n) for n in names].index(v)]))
    mode.pack(side="left")
    cur = cool.power_mode()
    if cur:
        mode.set(t(cur))
    _ultimate(app, body)

    from . import fans
    fans.section(app, p)

# ---------- Storage ----------
def storage(app, p):
    body = app.card(p, t("Quick cleanup"))
    rows = {}
    def item(key, title, desc, action, btn_text, warn=None):
        r = app.row(body, 6)
        txt = ctk.CTkFrame(r, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True)
        rows[key] = app.label(txt, title, 14)
        rows[key].pack(anchor="w")
        app.label(txt, desc, 12, muted=True, wrap=620).pack(anchor="w")
        def run():
            if warn and not app.ask(title, warn, warn=True):
                return
            rows[key].configure(text=title + "  -  " + t("Working..."))
            app.bg(action, lambda _: refresh(), lambda m: rows[key].configure(text=title + "  -  " + m))
        app.button(r, btn_text, run, primary=False, width=150).pack(side="right")
    titles = {"rb": t("Recycle Bin"), "hib": t("Hibernation file"), "dism": t("Old Windows update files"),
              "old": t("Previous Windows installation")}
    item("rb", titles["rb"], t("Deletes the files in the Recycle Bin for good."), space.empty_recycle_bin, t("Empty"))
    item("hib", titles["hib"], t("Turning off hibernation deletes hiberfil.sys. Hibernate and Fast Startup stop "
                                 "working until you turn it back on."), lambda: space.set_hibernate(False),
         t("Turn off"), t("Hibernate and Fast Startup will stop working. Continue?"))
    item("dism", titles["dism"], t("Removes superseded Windows components (DISM StartComponentCleanup). Takes "
                                   "several minutes. Installed updates can still be removed."), space.component_cleanup,
         t("Clean up"))
    item("old", titles["old"], t("Windows.old lets you go back to the previous Windows version. Remove it in "
                                 "Windows Settings > Storage > Temporary files."), space.open_storage_settings,
         t("Open settings"))
    def refresh():
        def work():
            return space.recycle_bin(), space.hiberfil_gb(), space.windows_old_gb()
        def show(res):
            (mb, n), hib, old = res
            rows["rb"].configure(text=f"{titles['rb']}  -  {mb} MB")
            rows["hib"].configure(text=f"{titles['hib']}  -  {hib} GB" if hib else f"{titles['hib']}  -  {t('Off')}")
            rows["dism"].configure(text=titles["dism"])
            rows["old"].configure(text=f"{titles['old']}  -  {old} GB" if old else f"{titles['old']}  -  {t('None')}")
        app.bg(work, show)
    refresh()

    body = app.card(p, t("Find unneeded files"), t("Tick what to look for and pick a drive (other drives: large old "
                    "files only). Folders and files named after an app on this PC are never listed. Nothing is "
                    "deleted automatically; ticked items go to the Recycle Bin after you confirm twice."))
    kinds = app.cfg.setdefault("clean_kinds", list(cleaner.DEFAULT_KINDS))
    labels = {"temp": "Temp files", "installer": "Old installers", "download": "Downloads", "video": "Videos",
              "photo": "Photos", "music": "Music", "personal": "My files", "large": "Large old files",
              "leftover": "Uninstalled app folders", "save": "Game saves"}
    boxes = ctk.CTkFrame(body, fg_color="transparent")
    boxes.pack(fill="x", pady=(0, 6))
    def toggle(k, var):
        if var.get() and k not in kinds:
            kinds.append(k)
        elif not var.get() and k in kinds:
            kinds.remove(k)
        app.save()
    for i, k in enumerate(cleaner.KINDS):
        var = ctk.BooleanVar(value=k in kinds)
        ctk.CTkCheckBox(boxes, text=t(labels[k]), variable=var, command=lambda k=k, v=var: toggle(k, v), width=150,
                        checkbox_width=18, checkbox_height=18, font=F(12), fg_color=ACCENT,
                        hover_color=ACCENT).grid(row=i // 5, column=i % 5, sticky="w", padx=(0, 8), pady=2)
    r = app.row(body)
    lbl = app.label(r, "", 12, muted=True)
    tree = app.table(body, [("name", t("Name")), ("size", t("Size (MB)")), ("age", t("Age (days)")),
                            ("reason", t("Reason")), ("path", t("Path"))], (220, 80, 80, 250, 300), 12,
                     {"temp": ACCENT, "installer": ACCENT, "large": WARN, "video": MUTED, "photo": MUTED,
                      "music": MUTED, "download": MUTED, "personal": WARN, "leftover": WARN, "save": WARN, "rec": ACCENT})
    # the tick box is a picture in the first column (larger than a text symbol); a click there ticks the row,
    # a double click on the rest of the row opens its folder
    tree.configure(selectmode="none", show="tree headings")
    tree.heading("#0", text="")
    tree.column("#0", width=46, minwidth=46, stretch=False)
    box = _tick_images(app)
    state = {"c": [], "on": set()}
    def mark(iid):
        tree.item(iid, image=box[iid in state["on"]])
    def summary():
        mb = sum(x["size_mb"] for x in state["c"] if x["path"] in state["on"])
        lbl.configure(text=t("{n} items, {s} selected ({mb} MB)", n=len(state["c"]), s=len(state["on"]), mb=round(mb)))
    def click(e):
        iid = tree.identify_row(e.y)
        if iid and tree.identify_column(e.x) == "#0":
            state["on"].symmetric_difference_update({iid})
            mark(iid)
            summary()
        return "break"
    def open_folder(e):
        iid = tree.identify_row(e.y)
        if iid and tree.identify_column(e.x) != "#0":
            import subprocess
            subprocess.Popen(["explorer", "/select,", iid] if os.path.exists(iid) else
                             ["explorer", os.path.dirname(iid)])
        return "break"
    tree.bind("<Button-1>", click)
    tree.bind("<Double-1>", open_folder)
    def select(which):
        state["on"] = {x["path"] for x in state["c"] if which == "all" or (which == "safe" and x["kind"] in ("temp", "installer"))}
        for iid in tree.get_children():
            mark(iid)
        summary()
    def fill(c):
        state["c"], state["on"] = c, set()
        tree.delete(*tree.get_children())
        for x in sorted(c, key=lambda x: -x["size_mb"]):
            tree.insert("", "end", iid=x["path"], tags=(x["kind"],), image=box[False], values=(
                os.path.basename(x["path"].rstrip("\\")) or x["path"], x["size_mb"], x["age_days"], x["reason"],
                os.path.dirname(x["path"].rstrip("\\"))))
        summary()
    try:
        drives = disk.drives() or ["C:"]
    except Exception:
        drives = ["C:"]
    pick = app.seg(r, drives)
    pick.set(drives[0])
    def scan():
        lbl.configure(text=t("Scanning..."))
        app.bg(lambda: cleaner.scan(pick.get(), list(kinds)), fill)
    def trash():
        sel = [x["path"] for x in state["c"] if x["path"] in state["on"]]
        whole = {x["path"] for x in state["c"] if x["kind"] in cleaner.WHOLE_FOLDER}
        picked = [x for x in state["c"] if x["path"] in state["on"]]
        risky = any(x["kind"] in ("save", "leftover", "personal", "photo", "video", "music") for x in picked)
        per = {}
        for x in picked:
            per[t(labels.get(x["kind"], x["kind"]))] = per.get(t(labels.get(x["kind"], x["kind"])), 0) + 1
        detail = "\n".join(f"  {k}: {v}" for k, v in per.items())
        mb = round(sum(x["size_mb"] for x in picked))
        if sel and app.ask(t("Recycle Bin"), t("Move {n} item(s) to the Recycle Bin?", n=len(sel)), warn=risky) and \
                app.ask(t("Check once more"), t("These {n} items ({mb} MB) go to the Recycle Bin:\n{d}\n\nYou can "
                        "restore them from the Recycle Bin until it is emptied. Continue?", n=len(sel), mb=mb,
                        d=detail), warn=True):
            lbl.configure(text=t("Moving to the Recycle Bin..."))
            app.bg(lambda: cleaner.trash(sel, whole), lambda n: (lbl.configure(text=t("Moved {n} file(s)", n=n)), scan()))
    pick.pack(side="left")
    app.button(r, t("Scan"), scan).pack(side="left", padx=8)
    lbl.pack(side="right")
    r2 = app.row(body, (6, 0))
    app.button(r2, t("Select all"), lambda: select("all"), primary=False, width=90).pack(side="left")
    app.button(r2, t("Select temp files and installers"), lambda: select("safe"), primary=False,
               tooltip=t("Ticks only temp files and old installers. Photos, videos, music, saves and large files are not ticked.")).pack(
        side="left", padx=6)
    app.button(r2, t("Select none"), lambda: select("none"), primary=False, width=90).pack(side="left")
    app.button(r2, t("Move selected to Recycle Bin"), trash).pack(side="right")
    app.tip(tree, t("Click the box to tick a row. Double-click a name to open its folder."))
    _recommend(app, body, state, fill_marks=lambda: ([mark(i) for i in tree.get_children()], summary()), tree=tree)

def _tick_images(app):
    """Unticked / ticked box pictures (22 px at 100% scaling), drawn 4x larger and scaled down for smooth corners."""
    if "_ticks" not in app.__dict__:
        from PIL import Image, ImageDraw, ImageTk
        px = round(22 * app._get_window_scaling())
        out = []
        for on in (False, True):
            S = px * 4
            im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            r = (S * 0.06, S * 0.06, S * 0.94, S * 0.94)
            if on:
                d.rounded_rectangle(r, radius=S * 0.2, fill=ACCENT)
                d.line([(S * 0.26, S * 0.52), (S * 0.43, S * 0.69), (S * 0.75, S * 0.33)], fill="#0e1116",
                       width=round(S * 0.11), joint="curve")
            else:
                d.rounded_rectangle(r, radius=S * 0.2, outline=MUTED, width=round(S * 0.08))
            out.append(ImageTk.PhotoImage(im.resize((px, px), Image.LANCZOS)))
        app._ticks = out
    return app._ticks

def _recommend(app, body, state, fill_marks, tree):
    """Ticks the scanned rows that match a fixed rule (exact copies, installers of installed apps, extracted
    archives, temp files...). Runs on this PC only."""
    r = app.row(body, (10, 0))
    out = app.label(body, "", 12, muted=True, wrap=880)
    def done(picks):
        for path, why in picks:
            state["on"].add(path)
            if tree.exists(path):
                tree.item(path, tags=("rec",))
                tree.set(path, "reason", why)
        fill_marks()
        out.configure(text=t("{n} items recommended (ticked and shown in green). Check them before moving.",
                             n=len(picks)) if picks else t("Nothing matched the rules."), text_color=ACCENT)
    def run():
        if not state["c"]:
            return out.configure(text=t("Scan first."), text_color=WARN)
        out.configure(text=t("Comparing files..."), text_color=MUTED)
        app.bg(lambda: cleaner.recommend(state["c"]), done, lambda m: out.configure(text=m, text_color=WARN))
    app.button(r, t("Recommend"), run).pack(side="left")
    app.tip(r, t("Ticks only clear cases: exact copies of another file in the list (the oldest stays), 'name (1)' "
                 "copies, installers of apps that are already installed, archives already extracted next to them, "
                 "installers unused for 3 months, temp files and folders of removed apps unchanged for 6 months."))
    out.pack(anchor="w", pady=(6, 0))

# ---------- Browsers ----------
BROWSER_TWEAKS = {
    "Edge startup boost": "Off stops Edge from preloading when you sign in.",
    "Edge background mode": "Off stops Edge from running after you close it.",
    "Edge sleeping tabs": "Puts unused tabs to sleep to save memory and CPU.",
    "Chrome background mode": "Off stops Chrome from running after you close it.",
    "Chrome Memory Saver": "Frees memory from inactive tabs.",
}

def browser_cache(app, p):
    body = app.card(p, t("Browser cache"), t("Deletes only cached web files. History, passwords, cookies and "
                    "bookmarks are kept. Close the browser first; sites load a bit slower the first time afterwards."))
    box = ctk.CTkFrame(body, fg_color="transparent", height=1)
    box.pack(fill="x")
    def fill(bs):
        for w in box.winfo_children():
            w.destroy()
        if not bs:
            app.label(box, t("No supported browser found."), muted=True).pack(anchor="w")
        for b in bs:
            r = app.row(box, 4)
            state = t("running") if b["running"] else ""
            app.label(r, f"{b['name']}  -  {b['size_mb']} MB  {state}", 14).pack(side="left")
            def clear(b=b):
                try:
                    br.clear_cache(b)
                except Exception as e:
                    app.info(b["name"], str(e))
                refresh()
            app.button(r, t("Clear cache"), clear, primary=False, width=130).pack(side="right")
    def refresh():
        app.bg(br.browsers, fill)
    refresh()

    body = app.card(p, t("Remove Microsoft Edge"), t("Uses the same method as Chris Titus WinUtil. Microsoft only "
                    "supports removing Edge in the European Economic Area, so Windows Update may reinstall it. "
                    "WebView2, which other apps need, is kept. Edge favorites and passwords are deleted."))
    r = app.row(body)
    st = app.label(r, "", 13)
    def refresh_edge():
        st.configure(text=t("Edge is installed.") if br.edge_installed() else t("Edge is not installed."))
    def remove():
        if not app.ask(t("Remove Microsoft Edge"), t("Edge, its favorites and saved passwords will be removed. "
                       "Make sure you have another browser. Continue?"), warn=True):
            return
        st.configure(text=t("Working..."))
        app.bg(br.remove_edge, lambda ok: (refresh_edge(), app.info(t("Remove Microsoft Edge"),
               t("Edge was removed.") if ok else t("Edge could not be removed."))))
    def reinstall():
        st.configure(text=t("Working..."))
        app.bg(br.reinstall_edge, lambda out: refresh_edge())
    app.button(r, t("Remove Edge"), remove, primary=False).pack(side="right")
    app.button(r, t("Reinstall Edge"), reinstall, primary=False).pack(side="right", padx=8)
    st.pack(side="left")
    refresh_edge()

def browser_policies(app, p):
    body = app.card(p, t("Browser settings"), t("These are set as browser policies, so the browser shows "
                    "'Managed by your organization'. Use Restore defaults to remove them."))
    for name, desc in BROWSER_TWEAKS.items():
        _tweak_switch(app, body, name, t(desc))
    def restore():
        tweaks.reset(list(BROWSER_TWEAKS))
        app.info(t("Browser settings"), t("Defaults restored. Restart the browser to apply."))
    app.button(app.row(body, (6, 0)), t("Restore defaults"), restore, primary=False).pack(side="left")


# ---------- Windows ----------
def windows(app, p):
    body = app.card(p, t("Windows settings"))
    _tweak_switch(app, body, "Game Mode", t("Stops Windows Update driver installs and restart prompts while gaming."))
    _tweak_switch(app, body, "Background game recording", t("Keeps recording the last minutes of every game. Off "
                  "saves FPS; Win+Alt+R still records on demand."))
    _tweak_switch(app, body, "Game Bar captures", t("Off turns off all Game Bar screenshots and recordings."))
    _tweak_switch(app, body, "Share updates with other PCs", t("Off: Windows Update downloads only from Microsoft and "
                  "does not upload to other PCs."))
    body = app.card(p, t("Memory integrity (Core isolation)"), t("A Windows security feature that blocks malicious "
                    "or unsigned drivers. Microsoft notes it can reduce performance in some games. Turning it off "
                    "lowers your protection: only do it if you understand the risk, and turn it back on after gaming."))
    r = app.row(body)
    lbl = app.label(r, t("Current: {s}", s=t(tweaks.hvci_state())))
    lbl.pack(side="left")
    def off():
        if app.ask(t("Lower security?"), t("Turning off memory integrity lets drivers that Windows would normally block "
                   "load into the kernel. Malware can use this to take full control of the PC.\n\nThe FPS gain is "
                   "usually small and depends on the game. A restart is required, and you should turn it back on "
                   "after gaming.\n\nTurn off memory integrity anyway?"), warn=True):
            tweaks.hvci_disable()
            lbl.configure(text=t("Current: {s}", s=t("off")) + " " + t("(restart needed)"))
    app.button(r, t("Turn off (not recommended)"), off, primary=False).pack(side="right", padx=4)
    def game_boot():
        from core import gameboot
        if app.ask(t("Game boot"), t("The PC restarts with memory integrity off. After you finish gaming the app asks "
                   "you to turn it back on (one more restart).\n\nWhile it is off, drivers Windows would normally "
                   "block can load. Save your work first.\n\nRestart now?"), warn=True):
            app.save()
            gameboot.start(app.cfg)
            app.save()
    r2 = app.row(body, (8, 0))
    app.button(r2, t("Game boot (restart without memory integrity)"), game_boot, primary=False).pack(side="left")
    app.label(r2, t("Memory integrity is read only when Windows starts, so this needs a restart."), 12,
              muted=True).pack(side="left", padx=10)
    app.button(r, t("Turn back on"), tweaks.open_core_isolation).pack(side="right")
    body = app.card(p, t("Background news"), t("Turns off the news feed in Windows 11 Widgets (or News and interests "
                    "on the Windows 10 taskbar) and the news on Edge's new tab page, using Windows and Edge policies. "
                    "Sign out or restart Edge to apply. Turn it back on here to remove the policies."))
    from core import news, services
    app.switch_row(body, t("Stop background news"), t("Widgets and Edge stop loading news in the background."),
                   news.is_off(), news.set_off, glyph="shield")
    body = app.card(p, t("Pause services during games"), t("These Windows services are stopped while a game runs and "
                    "started again when it closes. Nothing is disabled permanently. Xbox services are never touched "
                    "because Game Pass games need them."))
    chosen = app.cfg.setdefault("game_services", [])
    def pick(name, on):
        if on and name not in chosen:
            chosen.append(name)
        elif not on and name in chosen:
            chosen.remove(name)
        app.save()
    for name, (title, desc) in services.SERVICES.items():
        app.switch_row(body, t(title), t(desc), name in chosen, lambda on, n=name: pick(n, on))
    body = app.card(p, t("Microsoft's performance tips"), t("From Microsoft's guide 'Tips to improve PC performance in "
                    "Windows'. Each button opens the right Windows setting."))
    for title, target in ((t("Install Windows and driver updates"), "ms-settings:windowsupdate"),
                          (t("Scan for malware"), "windowsdefender://threat"),
                          (t("Optimize (defragment) drives"), "dfrgui.exe")):
        r = app.row(body, 3)
        app.label(r, title, 13).pack(side="left")
        app.button(r, t("Open"), lambda x=target: os.startfile(x), primary=False, width=90).pack(side="right")

# ---------- Hardware ----------
def hardware_page(app, p):
    body = app.card(p, t("Hardware report"), t("These settings live in the BIOS or need hardware changes; the app "
                                               "can only check them."))
    box = ctk.CTkFrame(body, fg_color="transparent", height=1)
    def work():
        out = []
        try:
            mods = hardware.ram_modules()
            speeds = "/".join(str(s) for s in sorted({m["mhz"] for m in mods}))
            out.append((t("Memory"), t("{n} module(s), {gb} GB, running at {mhz} MHz", n=len(mods),
                        gb=sum(m["gb"] for m in mods), mhz=speeds),
                        t("Single channel: add a matching module.") if len(mods) == 1 else
                        t("Compare with your RAM's rated XMP/EXPO speed and enable the profile in BIOS if it is lower.")))
        except Exception as e:
            out.append((t("Memory"), str(e), ""))
        try:
            cur, best, res = hardware.refresh_info()
            out.append((t("Display"), t("{res} at {cur} Hz (max {best} Hz)", res=res, cur=cur, best=best),
                        t("Use Fix in the System check widget to switch to the maximum.") if best > cur else ""))
        except Exception as e:
            out.append((t("Display"), str(e), ""))
        rb = hardware.rebar()
        out.append((t("Resizable BAR"), {"on": t("Enabled"), "off": t("Disabled"), None: t("Unknown (NVIDIA only)")}[rb],
                    t("Enable it in BIOS if supported; the gain depends on the game.") if rb == "off" else ""))
        return out
    def show(rows):
        for w in box.winfo_children():
            w.destroy()
        for title, value, hint in rows:
            r = ctk.CTkFrame(box, fg_color=CARD2, corner_radius=10)
            r.pack(fill="x", pady=4)
            app.label(r, title, 13, muted=True, width=130, anchor="w").pack(side="left", padx=12, pady=10)
            txt = ctk.CTkFrame(r, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, pady=8)
            app.label(txt, value, 14, bold=True).pack(anchor="w")
            if hint:
                app.label(txt, hint, 12, muted=True, wrap=600).pack(anchor="w")
    app.button(body, t("Run report"), lambda: app.bg(work, show)).pack(anchor="w")
    box.pack(fill="x", pady=(8, 0))

    body = app.card(p, t("Lag while charging"), t("Record while plugged in, then unplug and keep recording. If the "
                    "clock is much lower on AC with the performance limit below 100% at a normal temperature, suspect "
                    "BD PROCHOT or the charger."))
    r = app.row(body)
    log = app.console(body, 260)
    st = {"on": False, "s": None}
    def tick():
        if st["on"]:
            row = st["s"].sample(f"{datetime.now():%H:%M:%S}")
            app.write(log, "  ".join(f"{str(v):<6}" for v in row.values()))
            app.after(1000, tick)
    def toggle():
        st["on"] = not st["on"]
        btn.configure(text=t("Stop") if st["on"] else t("Start recording"))
        if st["on"]:
            st["s"] = Sampler()
            app.write(log, "time      AC     bat%  cpu%  MHz    limit%  temp", clear=True)
            tick()
        else:
            app.write(log, "\n" + st["s"].summary())
    def save():
        if st["s"] and (path := filedialog.asksaveasfilename(defaultextension=".csv")):
            st["s"].save(path)
    btn = app.button(r, t("Start recording"), toggle)
    btn.pack(side="left")
    app.button(r, t("Save CSV"), save, primary=False).pack(side="left", padx=8)
    from core import battery
    tips = app.details(body, t("Which charger to use"))
    for line in battery.CHARGER_TIPS:
        app.label(tips, "•  " + t(line), 12, wrap=820).pack(anchor="w", pady=1)
    app.label(tips, t("The exact wattage your laptop needs is on the maker's spec page (This PC > Details)."), 11,
              muted=True, wrap=820).pack(anchor="w", pady=(4, 0))

# ---------- About ----------
def about(app, p):
    repo = f"https://github.com/{REPO}"
    body = app.card(p, f"PC Optimizer {__version__}", t("Free and open source (MIT License). No ads, no accounts, no "
                                                        "telemetry."))
    r = app.row(body)
    app.button(r, t("Source code"), lambda: webbrowser.open(repo)).pack(side="left")
    app.button(r, t("Report a problem"), lambda: webbrowser.open(repo + "/issues"), primary=False).pack(side="left", padx=8)
    app.button(r, t("Support on GitHub Sponsors"), lambda: webbrowser.open(f"https://github.com/sponsors/{REPO.split('/')[0]}"),
               primary=False).pack(side="left")

    body = app.card(p, t("Appearance"))
    themes = {t("Follow Windows"): "system", t("Light"): "light", t("Dark"): "dark"}
    r = app.row(body)
    app.label(r, t("Theme"), 13).pack(side="left")
    th = app.seg(r, list(themes), lambda v: (app.cfg.__setitem__("theme", themes[v]), app.save(),
                                              note2.configure(text=t("Restart the app to apply."))))
    th.set(next(k for k, v in themes.items() if v == app.cfg.get("theme", "system")))
    th.pack(side="right")
    def tips_on(on):
        from . import kit
        kit.TIPS["on"] = on
        app.cfg["tooltips"] = on
        app.save()
    app.switch_row(body, t("Show tips when the pointer rests on an item"), "", app.cfg.get("tooltips", True), tips_on)
    from core import addons
    fonts = {t("Windows default"): None}
    fonts.update({t(v["title"]): k for k, v in addons.CATALOG.items() if v["kind"] == "font"})
    r = app.row(body, (4, 0))
    app.label(r, t("Font"), 13).pack(side="left")
    def pick_font(v):
        aid = fonts[v]
        def done(_=None):
            app.cfg["font"] = addons.CATALOG[aid]["family"] if aid else None
            app.save()
            note2.configure(text=t("Restart the app to apply."))
        if aid and not addons.installed(aid):
            if not app.ask(t("Font"), t("{name} ({lic}) is downloaded once (about 3 MB) from its author's GitHub page "
                           "and checked against a fingerprint built into this app. Download it?",
                           name=v, lic=addons.CATALOG[aid]["license"])):
                return
            note2.configure(text=t("Downloading..."))
            app.bg(lambda: addons.download(aid), done, lambda m: note2.configure(text=t("Download failed: {e}", e=m)))
        else:
            done()
    fs = app.seg(r, list(fonts), pick_font)
    fs.set(next((k for k, v in fonts.items() if v and addons.CATALOG[v]["family"] == app.cfg.get("font")),
                t("Windows default")))
    fs.pack(side="right")
    note2 = app.label(body, "", 12, muted=True)
    note2.pack(anchor="w")
    _background(app, body)

    body = app.card(p, t("Language"))
    langs = {"auto": t("Same as Windows"), "en": "English", "ko": lang_ko.NAME}
    seg = app.seg(app.row(body), list(langs.values()))
    seg.set(langs.get(app.cfg.get("lang", "auto"), langs["auto"]))
    seg.pack(side="left")
    note = app.label(body, "", 12, muted=True)
    note.pack(anchor="w", pady=(6, 0))
    def change(v):
        app.cfg["lang"] = next(k for k, n in langs.items() if n == v)
        app.save()
        note.configure(text=t("Restart the app to apply the language."))
    seg.configure(command=change)

    body = app.card(p, t("Updates"))
    app.switch_row(body, t("Check for updates on startup"), t("Sends one request to the GitHub Releases API. No "
                   "information about you or your PC is sent."), app.cfg.get("check_updates", True),
                   lambda on: (app.cfg.__setitem__("check_updates", on), app.save()))
    r = app.row(body, (6, 0))
    lbl = app.label(r, "", muted=True)
    lbl.pack(side="left")
    app.button(r, t("Check now"), lambda: app.check_update(True, lbl), primary=False).pack(side="right")

    body = app.card(p, t("What this app changes"))
    app.label(body, t("Every change is a standard Windows or browser setting. Turn switches off here to revert them; "
                      "uninstalling the app does not revert them. Cleaned files go to the Recycle Bin unless the button "
                      "says otherwise."), 12, wrap=860).pack(anchor="w")

def _background(app, body):
    """A picture (for example one from the Downloads folder) behind the pages."""
    from tkinter import filedialog
    from . import bgimage
    c = bgimage.cfg(app)
    r = app.row(body, (8, 0))
    app.label(r, t("Background picture"), 13).pack(side="left")
    name = app.label(r, os.path.basename(c["path"]) or t("None"), 12, muted=True)
    name.pack(side="left", padx=10)
    app.__dict__.setdefault("_bg_names", []).append(name)  # updated when the picture changes anywhere
    def pick():
        p = filedialog.askopenfilename(initialdir=bgimage.downloads(), title=t("Background picture"),
                                       filetypes=[(t("Images"), "*.jpg *.jpeg *.png *.bmp *.webp *.gif")])
        if p:
            app.background.set(os.path.normpath(p))
            name.configure(text=os.path.basename(p))
    def remove():
        app.background.set("")
        name.configure(text=t("None"))
    app.button(r, t("Remove"), remove, primary=False, width=70).pack(side="right")
    app.button(r, t("Choose picture"), pick, primary=False).pack(side="right", padx=6)
    r2 = app.row(body, (6, 0))
    app.label(r2, t("Picture strength"), 13).pack(side="left")
    s = ctk.CTkSlider(r2, from_=0.1, to=0.8, width=220, progress_color=ACCENT, button_color=ACCENT,
                      button_hover_color=ACCENT)
    s.set(c.get("strength", bgimage.STRENGTH))
    s.bind("<ButtonRelease-1>", lambda e: app.background.set(c["path"], round(s.get(), 2)))
    s.pack(side="right")
    r3 = app.row(body, (6, 0))
    app.label(r3, t("Picture position"), 13).pack(side="left")
    app.tip(r3, t("Shows a higher or lower part of the picture (a more left or right part for wide pictures)."))
    ps = ctk.CTkSlider(r3, from_=0, to=1, width=220, progress_color=ACCENT, button_color=ACCENT,
                       button_hover_color=ACCENT)
    ps.set(c.get("pos", bgimage.POS))
    ps.bind("<ButtonRelease-1>", lambda e: app.background.set(c["path"], pos=round(ps.get(), 2)))
    ps.pack(side="right")

def _ultimate(app, body):
    """Microsoft's hidden Ultimate Performance power plan (Windows 10 1803 and later)."""
    from core import power
    r = app.row(body, (10, 0))
    app.label(r, t("Ultimate Performance plan"), 13).pack(side="left")
    st = app.label(body, "", 12, muted=True, wrap=820)
    st.pack(anchor="w")
    def done(guid):
        st.configure(text=t("Added. It is now in Control Panel > Power Options, and Auto optimize uses it while a "
                            "listed app runs.") if guid else t("Windows does not offer this plan on this PC (for "
                            "example on laptops with Modern Standby, which only have Balanced)."),
                     text_color=MUTED if guid else WARN)
    app.button(r, t("Use now"), lambda: app.bg(lambda: power.unlock_ultimate(activate=True), done), primary=False,
               tooltip=t("Switches Windows to this plan now. Pick another plan in Control Panel > Power Options to "
                         "go back.")).pack(side="right")
    app.button(r, t("Unlock"), lambda: app.bg(power.unlock_ultimate, done), primary=False, tooltip=t(
        "Adds the hidden plan with: powercfg -duplicatescheme e9a42b02-d5df-448d-aa00-03f14749eb61. It removes "
        "small power-saving delays; it uses more power and is meant for desktops.")).pack(side="right", padx=6)

def background_card(app, p):
    """App management: change the picture behind this app's pages. Recent pictures from Downloads and Pictures
    are shown as thumbnails; click one to use it."""
    from . import bgimage
    body = app.card(p, t("App background"), t("The picture behind this app's pages (not the Windows wallpaper). "
                    "Click a recent picture from Downloads or Pictures, or choose any file."))
    _background(app, body)
    strip = ctk.CTkFrame(body, fg_color="transparent", height=1)
    strip.pack(fill="x", pady=(8, 0))
    note = app.label(body, t("Looking for pictures..."), 12, muted=True)
    note.pack(anchor="w")
    def find():
        from PIL import Image
        files = []
        for d in (bgimage.downloads(), os.path.join(os.path.expanduser("~"), "Pictures")):
            try:
                files += [e.path for e in os.scandir(d)
                          if e.is_file() and e.name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))]
            except OSError:
                pass
        files = sorted(set(files), key=lambda f: os.path.getmtime(f), reverse=True)[:8]
        out = []
        for f in files:
            try:
                im = Image.open(f)
                im.thumbnail((120, 72))
                out.append((f, im.convert("RGB")))
            except Exception:
                pass
        return out
    def show(items):
        if not strip.winfo_exists():
            return
        note.configure(text="" if items else t("No pictures in Downloads or Pictures yet."))
        if items:
            note.pack_forget()
        for f, im in items:
            img = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
            b = ctk.CTkButton(strip, image=img, text="", width=im.size[0] + 8, height=im.size[1] + 8,
                              corner_radius=8, fg_color=CARD2, hover_color=ACCENT,
                              command=lambda f=f: app.background.set(os.path.normpath(f)))
            b.pack(side="left", padx=(0, 6))
            app.tip(b, os.path.basename(f))
    app.bg(find, show, lambda m: note.configure(text=""))
