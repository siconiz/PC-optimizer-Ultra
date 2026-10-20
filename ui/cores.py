"""Dialog to choose CPU cores for an app."""
import customtkinter as ctk
from core.i18n import t
from .theme import BG, CARD, F

def ask_cores(app, topo, done):
    win = ctk.CTkToplevel(app, fg_color=BG)
    win.title(t("Choose CPU cores"))
    win.transient(app)
    win.grab_set()
    ctk.CTkLabel(win, text=t("P = performance core, E = efficiency core. Fewer cores can make an app slower; Windows "
                             "usually spreads work well on its own."), font=F(12), wraplength=460,
                 justify="left").pack(padx=16, pady=(14, 8), anchor="w")
    grid = ctk.CTkFrame(win, fg_color=CARD, corner_radius=10)
    grid.pack(padx=16, fill="x")
    boxes = []
    for c in range(topo["cpus"]):
        kind = "E" if c in topo["e"] else "P"
        b = ctk.CTkCheckBox(grid, text=f"{c} ({kind})", font=F(12), width=90)
        b.grid(row=c // 6, column=c % 6, padx=6, pady=6, sticky="w")
        boxes.append(b)
    def pick(cs):
        for i, b in enumerate(boxes):
            b.select() if i in cs else b.deselect()
    pick(topo["p"])
    r = ctk.CTkFrame(win, fg_color="transparent")
    r.pack(padx=16, pady=12, fill="x")
    for text, cs in ((t("Performance cores"), topo["p"]), (t("Efficiency cores"), topo["e"]),
                     (t("All"), list(range(topo["cpus"])))):
        if cs:
            app.button(r, text, lambda c=cs: pick(c), primary=False, width=120).pack(side="left", padx=(0, 6))
    def ok():
        cs = [i for i, b in enumerate(boxes) if b.get()]
        if cs:
            done(cs)
        win.destroy()
    app.button(r, t("Apply"), ok, width=90).pack(side="right")
