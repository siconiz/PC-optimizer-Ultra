"""Dashboard top: this PC (details, maker spec page, benchmark links) and the computer scan."""
import webbrowser
import customtkinter as ctk
from core import driver, gpuinfo, scan as scan_core, sysinfo
from core.i18n import t
from .theme import ACCENT, BORDER, CARD2, MUTED, TEXT, WARN, F

def pc_card(app, page):
    """Compact 'This PC' card: name, one spec line, live stats chips, graphics driver status, details on demand."""
    body = app.card(page, t("This PC"), tooltip=t("Model, motherboard, BIOS, CPU, memory slots and graphics. Open "
                    "Details for everything, the maker's spec page and PassMark comparisons."))
    top = app.row(body)
    head = app.label(top, t("Checking..."), 14, bold=True)
    head.pack(side="left")
    sub = app.label(body, "", 12, muted=True, wrap=860)
    sub.pack(anchor="w")
    drv = app.label(body, "", 11, muted=True, wrap=860)
    drv.pack(anchor="w")
    _live(app, body)
    adv = app.details(body, t("Details"))
    links = app.row(adv, (0, 6))
    grid = ctk.CTkFrame(adv, fg_color="transparent", height=1)
    grid.pack(fill="x")
    def show(res):
        info, gpus = res
        name = " ".join(x for x in (info["maker"], info["family"] or info["model"]) if x) or t("Custom-built PC")
        head.configure(text=name)
        sub.configure(text=f"{info['cpu']}  ·  {info['ram_gb']} GB RAM  ·  " + ", ".join(gpus))
        app._sysinfo_short = "  ".join(x for x in (info["cpu"].replace("(R)", "").replace("(TM)", ""),
                                                   f"{info['ram_gb']:.0f}GB RAM", gpus[0] if gpus else "") if x)
        rows = [(t("Type"), t("Laptop") if info["laptop"] else t("Desktop")),
                (t("Model"), " ".join(x for x in (info["maker"], info["model"]) if x) or "-"),
                (t("Motherboard"), " ".join(x for x in (info["board_maker"], info["board"]) if x) or "-"),
                (t("BIOS"), info["bios"] or "-"),
                (t("Processor"), t("{cpu} ({c} cores, {th} threads)", cpu=info["cpu"], c=info["cores"], th=info["threads"])),
                (t("Memory"), t("{gb} GB, {used} of {slots} slots used", gb=info["ram_gb"], used=len(info["modules"]),
                                slots=info["slots"] or "?"))]
        rows += [("  " + (m["slot"] or "-"), f"{m['gb']} GB  {m['mhz'] or '-'} MHz  {m['maker']} {m['part']}".strip())
                 for m in info["modules"]]
        rows += [(t("Graphics"), g) for g in gpus]
        for i, (k, v) in enumerate(rows):
            app.label(grid, k, 12, muted=True).grid(row=i, column=0, sticky="w", padx=(0, 16), pady=1)
            app.label(grid, v, 12).grid(row=i, column=1, sticky="w", pady=1)
        app.button(links, t("Maker's spec page"), lambda: webbrowser.open(sysinfo.spec_link(info)),
                   primary=False).pack(side="left")
        part = next((m["part"] for m in info["modules"] if m["part"]), "")
        names = ["CPU"] + [(g.split()[0].replace("(R)", "") if len(gpus) > 1 else "GPU") for g in gpus] + (["RAM"] if part else [])
        for name, (_, url) in zip(names, sysinfo.bench_links(info["cpu"], gpus, part)):
            app.button(links, t("Compare {x}", x=name), lambda u=url: webbrowser.open(u), primary=False, width=100,
                       tooltip=t("Opens PassMark's public chart for this part in your browser.")).pack(side="left", padx=(6, 0))
    def work():
        gpus = [g["name"] for g in gpuinfo.adapters() if g["vendor"] != "Other"]
        return sysinfo.details(), gpus
    app.bg(work, show, lambda m: head.configure(text=m))
    def show_drv(ds):
        parts = [t("{gpu} driver {v} ({d})", gpu=d["name"].split(" ")[0], v=d["version"], d=d["date"]) + "  " +
                 (t("may be out of date") if d["old"] else t("recent")) for d in ds]
        drv.configure(text="   ·   ".join(parts), text_color=WARN if any(d["old"] for d in ds) else MUTED)
        if ds:
            app.tip(drv, t("Checked by driver date: GPU makers have no public 'latest version' service. Drivers older "
                           "than 6 months are flagged. Click to open the maker's driver page."))
            drv.configure(cursor="hand2")
            drv.bind("<Button-1>", lambda e: webbrowser.open(ds[0]["url"]))
    app.bg(driver.drivers, show_drv, lambda m: None)

def _live(app, body):
    """CPU / RAM / GPU / power tiles (big number, details, bar) like version 0.1; updated every 1.5 s while the
    dashboard is visible."""
    import psutil
    grid = ctk.CTkFrame(body, fg_color="transparent", height=1)
    grid.pack(fill="x", pady=(10, 2))
    grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="tile")
    tiles = {}
    for i, key in enumerate(("CPU", "RAM", "GPU", "Power")):
        tile = ctk.CTkFrame(grid, fg_color=CARD2, corner_radius=12)
        tile.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0 if i == 3 else 4))
        ctk.CTkLabel(tile, text=t(key), font=F(12), text_color=MUTED).pack(anchor="w", padx=14, pady=(10, 0))
        val = ctk.CTkLabel(tile, text="--", font=F(24, "bold"), text_color=TEXT)
        val.pack(anchor="w", padx=14)
        sub = ctk.CTkLabel(tile, text="", font=F(12), text_color=MUTED)
        sub.pack(anchor="w", padx=14)
        bar = ctk.CTkProgressBar(tile, progress_color=ACCENT, fg_color=BORDER, height=6)
        bar.set(0)
        bar.pack(fill="x", padx=14, pady=(6, 12))
        tiles[key] = (val, sub, bar)
    def put(key, value, detail, frac, warn=False):
        val, sub, bar = tiles[key]
        val.configure(text=value)
        sub.configure(text=detail)
        bar.set(max(0.0, min(1.0, frac)))
        bar.configure(progress_color=WARN if warn else ACCENT)
    try:
        from core.diag import Sampler
        sampler = Sampler()
    except Exception:
        sampler = None
    try:
        usage = gpuinfo.Usage()
    except Exception:
        usage = None
    def tick():
        r = app.cached("sampler", lambda: sampler.sample("", record=False), {}) if sampler else {}
        c = r.get("cpu_pct", psutil.cpu_percent())
        hw = getattr(app, "hw", None)
        temp = hw.cpu_temp() if hw else None
        put("CPU", f"{c:.0f}%", "  ".join(x for x in (f"{temp:.0f}°C" if temp else "",
                                                      f"{r['mhz']} MHz" if r.get("mhz") else "") if x), c / 100, c > 90)
        m = psutil.virtual_memory()
        put("RAM", f"{m.percent:.0f}%", f"{(m.total - m.available) / 2**30:.1f} / {m.total / 2**30:.0f} GB",
            m.percent / 100, m.percent > 85)
        gs = [g for g in app.cached(("gpu", id(usage)), lambda: gpuinfo.snapshot(usage), []) if g["util"] is not None] if usage else []
        if gs:
            g = max(gs, key=lambda g: g["util"] or 0)
            name = g["name"].replace("NVIDIA GeForce ", "").replace("AMD Radeon", "Radeon")
            put("GPU", f"{g['util']:.0f}%", "  ".join(x for x in (f"{g['temp']:.0f}°C" if g["temp"] else "", name) if x),
                g["util"] / 100)
        b = psutil.sensors_battery()
        if b:
            put("Power", f"{b.percent:.0f}%", t("Charging") if b.power_plugged else t("On battery"), b.percent / 100,
                b.percent < 20 and not b.power_plugged)
        else:
            put("Power", t("AC"), t("Plugged in"), 1)
    app.every(1500, tick, grid, "Dashboard")

def scan_card(app, page):
    body = app.card(page, t("Computer scan"), t("Checks this PC and turns on the settings that fit it best. Only safe "
                    "settings are ticked; you can untick anything before applying."))
    top = app.row(body)
    status = app.label(top, t("Not scanned yet"), muted=True)
    status.pack(side="left")
    lst = app.scroll_box(body, 300)  # long result lists scroll inside the card
    state = {"items": [], "vars": []}
    def show(items):
        for w in lst.winfo_children():
            w.destroy()
        state["items"], state["vars"] = items, []
        fixable = [i for i in items if i["fix"] and not i.get("kind")]
        n = sum(not i.get("kind") for i in items)
        status.configure(text=t("{n} suggestion(s)", n=n) if n else t("Everything looks good"),
                         text_color=WARN if n else ACCENT)
        for it in items:
            r = ctk.CTkFrame(lst, fg_color=CARD2, corner_radius=8, border_width=1, border_color=BORDER)
            r.pack(fill="x", pady=3)
            var = ctk.BooleanVar(value=it["default"])
            state["vars"].append(var)
            if it["fix"] and not it.get("kind"):
                ctk.CTkCheckBox(r, text="", variable=var, width=24, checkbox_width=20, checkbox_height=20,
                                fg_color=ACCENT).pack(side="left", padx=(12, 0))
            else:
                ctk.CTkLabel(r, text="i", font=F(14, "bold"), text_color=MUTED, width=24).pack(side="left", padx=(12, 0))
            txt = ctk.CTkFrame(r, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, padx=8, pady=6)
            app.label(txt, it["title"], 13, bold=True).pack(anchor="w")
            app.label(txt, it["detail"], 12, muted=True, wrap=680).pack(anchor="w")
            if it.get("kind") == "power":  # a choice, not a fix: the rows save as soon as they change
                from .boost import power_rows
                power_rows(app, txt)
            if it.get("tip"):
                app.tip(r, it["tip"])
        apply_btn.configure(state="normal" if fixable else "disabled")
        app.fit_scroll(lst)
    def run():
        status.configure(text=t("Scanning..."), text_color=MUTED)
        app.bg(lambda: scan_core.run(app.cfg), show)
    def apply():
        chosen = [it for it, v in zip(state["items"], state["vars"]) if it["fix"] and not it.get("kind") and v.get()]
        def done(res):
            n, failed, restart = res
            app.save()
            app.set_autopilot(app.cfg.get("autopilot", True))
            msg = t("{n} setting(s) applied.", n=n) + (" " + t("{n} failed.", n=failed) if failed else "")
            if restart:
                msg += " " + t("Restart Windows to finish.")
            app.info(t("Computer scan"), msg)
            run()
        app.bg(lambda: scan_core.apply(chosen), done)
    apply_btn = app.button(top, t("Apply selected"), apply, state="disabled")
    apply_btn.pack(side="right")
    app.button(top, t("Scan"), run, primary=False).pack(side="right", padx=6)

def banner(app, page):
    """Reminder while a game boot is active (memory integrity off)."""
    if not app.cfg.get("game_boot"):
        return
    from core import gameboot
    body = app.card(page, t("Game boot is active"))
    msg = t("Memory integrity is still on after the restart. It may be locked by your organization or the PC maker, "
            "so it cannot be turned off here.") if gameboot.running() else t("Memory integrity is off so games run a "
            "little faster. Turn it back on when you are done gaming: it protects Windows from malicious drivers.")
    app.label(body, msg, 12, wrap=860).pack(anchor="w", pady=(0, 6))  # must be visible, not only a tooltip
    r = app.row(body)
    def finish(restart):
        gameboot.finish(app.cfg, restart)
        app.save()
        body.master.destroy()
    app.button(r, t("Turn back on and restart"), lambda: finish(True)).pack(side="left")
    app.button(r, t("Turn back on at next restart"), lambda: finish(False), primary=False).pack(side="left", padx=8)
