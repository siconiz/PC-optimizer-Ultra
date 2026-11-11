"""CPU & Memory page: running apps with cores / priority / efficiency mode / RAM trim, and memory tools."""
import customtkinter as ctk
from core import memory as mem, procs
from core.i18n import t
from .cores import ask_cores
from .theme import ACCENT, CARD2, HOVER2, WARN

def page(app, p):
    topo = procs.topology()
    # ---- memory overview ----
    body = app.card(p, t("Memory usage"), t("Standby cache is file data Windows keeps in RAM to open things faster. "
                    "It is handed to apps instantly when they need memory, so it is not wasted memory."))
    grid = ctk.CTkFrame(body, fg_color="transparent")
    grid.pack(fill="x")
    vals = {}
    for i, (k, n) in enumerate([("used", t("In use")), ("available", t("Available")), ("commit", t("Committed")),
                                ("standby", t("Standby cache")), ("modified", t("Modified"))]):
        grid.grid_columnconfigure(i, weight=1, uniform="m")
        f = ctk.CTkFrame(grid, fg_color=CARD2, corner_radius=10)
        f.grid(row=0, column=i, sticky="ew", padx=3)
        app.label(f, n, 12, muted=True).pack(anchor="w", padx=12, pady=(8, 0))
        vals[k] = app.label(f, "-", 20, bold=True)
        vals[k].pack(anchor="w", padx=12, pady=(0, 8))
    r = app.row(body, (8, 0))
    out = app.label(r, "", 12, muted=True)
    def free():
        out.configure(text=t("Working..."), text_color=ACCENT)
        app.bg(procs.free_ram, lambda mb: out.configure(text=t("Freed {mb} MB of RAM.", mb=mb)),
               lambda m: out.configure(text=m, text_color=WARN))
    app.button(r, t("Free up RAM"), free).pack(side="left")
    out.pack(side="left", padx=10)
    app.label(body, t("Free up RAM moves idle memory of background apps out of RAM and empties the standby cache. "
                      "The app in front and Windows itself are not touched. Use it before loading a large game or AI "
                      "model; background apps may react a little slower the next time you switch to them."),
              12, muted=True, wrap=820).pack(anchor="w", pady=(6, 0))
    r = app.row(body, (8, 0))
    app.label(r, t("Free up RAM automatically"), 13).pack(side="left")
    every = {t("Off"): 0, t("Every 30 minutes"): 30, t("Every hour"): 60, t("Every 2 hours"): 120,
             t("Every 4 hours"): 240}
    def set_every(v):
        app.cfg["ram_every"] = every[v]
        app._ram_at = __import__("time").monotonic()
        app.save()
    seg = app.seg(r, list(every), set_every)
    seg.set(next((k for k, v in every.items() if v == app.cfg.get("ram_every", 0)), t("Off")))
    seg.pack(side="right")
    app.tip(r, t("Runs Free up RAM on a timer while this app is open. Games and apps in the boost list are not "
                 "trimmed. Each run is listed in the Auto optimize log."))

    # ---- running apps ----
    kind = (t("{n} logical processors: {p} on performance cores, {e} on efficiency cores", n=topo["cpus"],
              p=len(topo["p"]), e=len(topo["e"])) if topo["e"] else t("{n} logical processors", n=topo["cpus"]))
    body = app.card(p, t("Running apps"), kind + ". " + t("Select an app to choose its CPU cores, priority or "
                    "efficiency mode. These last until the app closes; use the Boost page to apply them every time."))
    tree = app.table(body, [("name", t("App")), ("cpu", "CPU %"), ("mb", t("Memory (MB)")), ("n", t("Processes"))],
                     (320, 100, 120, 100), 12)
    state = {"apps": {}}
    def refresh():
        apps = procs.apps()[:40]
        state["apps"] = {a["name"]: a for a in apps}
        keep = set(tree.selection())
        tree.delete(*tree.get_children())
        for a in apps:
            tree.insert("", "end", iid=a["name"], values=(a["name"], f"{a['cpu']:.1f}", round(a["mb"]), len(a["pids"])))
        tree.selection_set([i for i in keep if i in state["apps"]])
    def chosen():
        return [state["apps"][i] for i in tree.selection() if i in state["apps"]]
    def act(fn, *args):
        msgs = []
        for a in chosen():
            if a["protected"]:
                msgs.append(t("{name} is part of Windows and cannot be ended here.", name=a["name"]))
            else:
                fn(a["pids"], *args)
        info.configure(text="\n".join(msgs) or t("Applied."), text_color=WARN if msgs else ACCENT)
    adv = app.details(body)
    r = app.row(adv)
    app.button(r, t("Cores..."), lambda: chosen() and ask_cores(app, topo, lambda cs: act(procs.set_cores, cs)),
               primary=False, width=90).pack(side="left")
    pri = ctk.CTkOptionMenu(r, values=[t(k) for k in procs.PRIORITIES], width=140, height=32, fg_color=CARD2, button_color=CARD2, button_hover_color=HOVER2,
                            command=lambda v: act(procs.set_priority, next(k for k in procs.PRIORITIES if t(k) == v)))
    pri.set(t("Priority"))
    pri.pack(side="left", padx=6)
    app.button(r, t("Efficiency mode"), lambda: act(procs.set_efficiency, True), primary=False).pack(side="left")
    app.button(r, t("Normal mode"), lambda: act(procs.set_efficiency, False), primary=False).pack(side="left", padx=6)
    app.button(r, t("Trim RAM"), lambda: act(procs.trim), primary=False, width=90).pack(side="left")
    def end():
        for a in chosen():
            if app.ask(t("End app"), t("End {name}? Unsaved work in it will be lost.", name=a["name"]), warn=True):
                try:
                    mem.end_app(a)
                except Exception as e:
                    info.configure(text=str(e), text_color=WARN)
    app.button(r, t("End"), end, primary=False, width=70).pack(side="left", padx=6)
    info = app.label(adv, t("Efficiency mode (same as Task Manager) runs a background app slower and cooler so the "
                             "app you use gets more CPU."), 12, muted=True, wrap=820)
    info.pack(anchor="w", pady=(6, 0))
    def tick():
        s = mem.stats()
        for k in vals:
            vals[k].configure(text=f"{s[k]} GB" if s.get(k) is not None else "-")
        if s.get("commit") and s.get("limit"):
            vals["commit"].configure(text=f"{s['commit']} / {s['limit']} GB")
        refresh()
    app.every(2000, tick, tree, "CPU & Memory")

    # ---- page file and diagnostics ----
    body = app.card(p, t("Virtual memory and RAM health"))
    pf = app.label(body, t("Checking..."), 13, wrap=820)
    pf.pack(anchor="w")
    rec = app.label(body, "", 13, wrap=820)
    rec.pack(anchor="w", pady=(6, 0))
    r = app.row(body, (8, 0))
    app.button(r, t("Virtual memory settings"), mem.open_virtual_memory_settings, primary=False).pack(side="left")
    app.button(r, t("Windows Memory Diagnostic"), mem.open_memory_diagnostic, primary=False).pack(side="left", padx=8)
    app.label(body, t("Windows Memory Diagnostic tests your RAM for errors after a restart. Run it if you get random "
                      "crashes or blue screens."), 12, muted=True, wrap=820).pack(anchor="w", pady=(6, 0))
    def show_pf(res):
        auto, files = res
        if not files:
            pf.configure(text=t("No page file. Some games crash when they run out of memory without one; "
                                "consider letting Windows manage it."), text_color=WARN)
            return
        lines = [t("Managed by Windows") if auto else t("Custom size")]
        lines += [t("{path}: {size} MB, {used} MB used (peak {peak} MB)", path=f["path"], size=f["size_mb"],
                    used=f["used_mb"], peak=f["peak_mb"]) for f in files]
        pf.configure(text="\n".join(lines))
    app.bg(mem.pagefile, show_pf, lambda m: pf.configure(text=m))
    def show_rec(r):
        rec.configure(text=t("Recommended: let Windows manage the size. If you set it yourself, use at least {a} GB "
                             "initial and {b} GB maximum ({ram} GB RAM, peak use since start-up {peak} GB, Microsoft's "
                             "sizing rules).", a=r["initial"], b=r["max"], ram=r["ram"], peak=r["peak"]))
    app.bg(mem.recommend_pagefile, show_rec, lambda m: None)
