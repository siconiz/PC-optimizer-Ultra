"""System tabs: startup apps, notifications and visual effects."""
import os, tkinter as tk
from tkinter import filedialog
from core import desktop, startup
from core.i18n import t
from .theme import ACCENT, BG, CARD2, HOVER2, MUTED, ON_ACCENT, TEXT, F

def startup_tab(app, p):
    body = app.card(p, t("Startup apps"), t("Apps that start when you sign in. Turning one off works like Task "
                    "Manager: the entry stays and you can turn it back on. Right-click for more."))
    top = app.row(body)
    count = app.label(top, "", 12, muted=True)
    count.pack(side="left")
    tree = app.table(body, [("name", t("Name")), ("state", t("Status")), ("scope", t("For")), ("cmd", t("Command"))],
                     (220, 90, 100, 480), 12, {"off": MUTED, "on": ACCENT})
    state = {"items": []}
    def fill(items=None):
        state["items"] = items if items is not None else startup.entries()
        tree.delete(*tree.get_children())
        for i, e in enumerate(state["items"]):
            tree.insert("", "end", iid=str(i), tags=("on" if e["enabled"] else "off",),
                        values=(e["name"], t("On") if e["enabled"] else t("Off"), t(e["scope"]), e["command"]))
        n = sum(e["enabled"] for e in state["items"])
        count.configure(text=t("{n} of {total} on", n=n, total=len(state["items"])))
    def sel():
        return [state["items"][int(i)] for i in tree.selection()]
    def toggle(on):
        for e in sel():
            startup.set_enabled(e, on)
        fill(state["items"])
    def remove():
        es = sel()
        if es and app.ask(t("Remove"), t("Remove {n} startup item(s) for good? Turning it off is usually enough.",
                                       n=len(es)), warn=True):
            for e in es:
                try:
                    startup.remove(e)
                except Exception as ex:
                    app.info(e["name"], str(ex))
            fill()
    def locate():
        for e in sel()[:1]:
            path = e["target"]
            if path and os.path.exists(path):
                __import__("subprocess").Popen(["explorer", "/select,", path])
    def add():
        if path := filedialog.askopenfilename(filetypes=[("exe", "*.exe")]):
            startup.add(path.replace("/", "\\"))
            fill()
    menu = tk.Menu(tree, tearoff=0, bg=CARD2, fg=TEXT, activebackground=ACCENT, activeforeground=BG,
                   font=(F(12).cget("family"), 10))
    menu.add_command(label=t("Turn on"), command=lambda: toggle(True))
    menu.add_command(label=t("Turn off"), command=lambda: toggle(False))
    menu.add_command(label=t("Open file location"), command=locate)
    menu.add_separator()
    menu.add_command(label=t("Remove"), command=remove)
    def popup(e):
        iid = tree.identify_row(e.y)
        if iid:
            if iid not in tree.selection():
                tree.selection_set(iid)
            menu.tk_popup(e.x_root, e.y_root)
    tree.bind("<Button-3>", popup)
    tree.bind("<Double-1>", lambda e: sel() and toggle(not sel()[0]["enabled"]))
    app.button(top, t("Add app"), add, primary=False, width=100).pack(side="right")
    app.button(top, t("Turn off"), lambda: toggle(False), primary=False, width=90).pack(side="right", padx=6)
    app.button(top, t("Turn on"), lambda: toggle(True), width=90).pack(side="right")
    app.bg(startup.entries, fill, lambda m: count.configure(text=m))
    adv = app.details(body)
    app.label(adv, t("Apps from the Microsoft Store and scheduled tasks can also start with Windows. Those are in "
                     "Windows Settings."), 12, muted=True, wrap=820).pack(anchor="w")
    app.button(app.row(adv, (4, 0)), t("Open startup settings"), lambda: os.startfile("ms-settings:startupapps"),
               primary=False).pack(side="left")

def desktop_tab(app, p):
    body = app.card(p, t("Notifications"))
    app.switch_row(body, t("Notifications"), t("All app and system notifications. Turning them off also stops "
                   "banners during games."), desktop.notifications_on(), desktop.set_notifications)
    for name in desktop.TIPS:
        app.switch_row(body, t(name), "", desktop.tip_on(name), lambda on, n=name: desktop.set_tip(n, on))
    adv = app.details(body, t("Per app"))
    box = app.scroll_box(adv, 260)
    def fill(items):
        for w in box.winfo_children():
            w.destroy()
        if not items:
            app.label(box, t("No apps have sent notifications yet."), 12, muted=True).pack(anchor="w")
        for aid, name, on in items:
            app.switch_row(box, name, "", on, lambda v, a=aid: desktop.set_app_notifications(a, v))
        app.fit_scroll(box)
    app.bg(desktop.app_notifications, fill, lambda m: None)

    body = app.card(p, t("Visual effects"), t("Turning effects off makes Windows feel snappier on slow PCs and saves a "
                    "little GPU work. Text smoothing is not touched."))
    try:
        fx = desktop.effects()
    except Exception:
        fx = {}
    descs = {"Animations": t("Window, menu and taskbar animations."), "Transparency": t("See-through taskbar, Start "
             "and windows."), "Shadows": t("Shadows under windows and menus.")}
    for name, desc in descs.items():
        app.switch_row(body, t(name), desc, fx.get(name, True), lambda on, n=name: desktop.set_effect(n, on))
    app.button(app.row(body, (6, 0)), t("All visual effects..."), desktop.open_performance_options,
               primary=False).pack(side="left")
