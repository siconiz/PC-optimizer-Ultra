"""Graphics & Games page: the graphics driver's own 3D settings (NVIDIA / AMD / Intel), applied to all games."""
import customtkinter as ctk
from core import gpudrv, gpuinfo
from core.i18n import t
from .theme import CARD2, HOVER2, TEXT, WARN, F

APPS = {"NVIDIA": "NVIDIA Control Panel / NVIDIA app", "AMD": "AMD Software: Adrenalin Edition",
        "Intel": "Intel Graphics Software / Arc Control"}

def page(app, p):
    try:
        vendors = sorted({a["vendor"] for a in gpuinfo.adapters()} & set(gpudrv.VENDORS))
    except Exception:
        vendors = []
    for v in vendors:
        _card(app, p, v)

def _card(app, p, vendor):
    body = app.card(p, t("{v} driver settings", v=vendor), t(
        "Changes the driver's global 3D settings (all games), the same ones {app} shows. A game's own profile in "
        "that app can still override them.", app=APPS[vendor]))
    status = app.label(body, t("Reading the driver settings..."), 12, muted=True)
    status.pack(anchor="w")
    rows = ctk.CTkFrame(body, fg_color="transparent", height=1)
    rows.pack(fill="x")
    def apply(key, value):
        status.pack(anchor="w", before=rows)
        status.configure(text=t("Saving..."), text_color=TEXT)
        app.bg(lambda: gpudrv.open_vendor(vendor).set(key, value),
               lambda _: status.configure(text=t("Saved. Restart a running game to use it.")),
               lambda m: status.configure(text=t("Could not change it: {e}", e=m), text_color=WARN))
    def show(items):
        if not rows.winfo_exists():
            return
        if items:
            status.pack_forget()
        else:
            status.configure(text=t("This driver does not offer these settings."))
        for it in items:
            r = app.row(rows, 3)
            app.label(r, t(it["title"]), 13).pack(side="left")
            if it["options"] == gpudrv.FPS:
                _fps(app, r, it, apply)
                continue
            labels = {t(lbl): v for lbl, v in it["options"]}
            m = ctk.CTkOptionMenu(r, values=list(labels), width=260, height=30, font=F(13), dropdown_font=F(13),
                                  fg_color=CARD2, button_color=CARD2, button_hover_color=HOVER2, text_color=TEXT,
                                  corner_radius=8, command=lambda lbl, k=it["key"], lb=labels: apply(k, lb[lbl]))
            m.set(next((k for k, v in labels.items() if v == it["value"]), t("Custom")))
            m.pack(side="right")
    def load():
        try:
            return gpudrv.open_vendor(vendor).settings()
        except gpudrv.NoDriver:
            return None
    def loaded(items):
        if items is None:
            status.configure(text=t("The {v} graphics driver is not installed, or it is too old for these settings. "
                                    "Install the latest driver from {v}'s website.", v=vendor), text_color=WARN)
        else:
            show(items)
    app.bg(load, loaded,
           lambda m: status.configure(text=t("The {v} driver did not answer: {e}", v=vendor, e=m), text_color=WARN))

def _fps(app, r, it, apply):
    e = ctk.CTkEntry(r, width=70, height=30, corner_radius=8, placeholder_text=t("Off"))
    if it["value"]:
        e.insert(0, str(it["value"]))
    def set_():
        v = e.get().strip()
        if v.isdigit() and 0 <= int(v) <= 1000:
            apply(it["key"], int(v))
    app.button(r, t("Off"), lambda: (e.delete(0, "end"), apply(it["key"], 0)), primary=False, width=60).pack(side="right")
    app.button(r, t("Apply"), set_, primary=False, width=70).pack(side="right", padx=6)
    app.label(r, "FPS", 12, muted=True).pack(side="right")
    e.pack(side="right", padx=4)
