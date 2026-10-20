"""PC Optimizer downloadable widget: wallpaper (pick an image, rotate a folder, or a plain color)."""
import ctypes, os, random
from tkinter import filedialog
from core.i18n import t

SPI_GET, SPI_SET, SAVE = 0x0073, 0x0014, 0x01 | 0x02
IMAGES = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

def current():
    buf = ctypes.create_unicode_buffer(520)
    ctypes.windll.user32.SystemParametersInfoW(SPI_GET, len(buf), buf, 0)
    return buf.value

def set_wallpaper(path):
    ctypes.windll.user32.SystemParametersInfoW(SPI_SET, 0, path, SAVE)  # "" = plain background color

def build(app, body):
    cfg = app.cfg.setdefault("wallpaper", {"folder": "", "minutes": 0})
    lbl = app.label(body, "", 12, muted=True, wrap=820)
    lbl.pack(anchor="w")
    def refresh():
        lbl.configure(text=t("Current: {p}", p=current() or t("plain color")))
    r = app.row(body, (6, 0))
    def pick():
        if p := filedialog.askopenfilename(filetypes=[(t("Images"), " ".join("*" + e for e in IMAGES))]):
            set_wallpaper(os.path.normpath(p))
            refresh()
    def plain():
        set_wallpaper("")
        refresh()
    def folder():
        if p := filedialog.askdirectory():
            cfg["folder"] = os.path.normpath(p)
            app.save()
            rotate(once=True)
    def rotate(once=False):
        files = [os.path.join(cfg["folder"], f) for f in os.listdir(cfg["folder"])
                 if f.lower().endswith(IMAGES)] if cfg["folder"] and os.path.isdir(cfg["folder"]) else []
        if files:
            set_wallpaper(random.choice(files))
            refresh()
    def tick():
        if not body.winfo_exists():
            return
        if cfg.get("minutes"):
            rotate()
            app.after(cfg["minutes"] * 60000, tick)
    app.button(r, t("Choose image"), pick).pack(side="left")
    app.button(r, t("Random from folder"), folder, primary=False).pack(side="left", padx=6)
    app.button(r, t("Plain color (lightest)"), plain, primary=False).pack(side="left")
    opts = {t("Off"): 0, t("Every 15 min"): 15, t("Every hour"): 60}
    r2 = app.row(body, (6, 0))
    app.label(r2, t("Change automatically while the app is open:"), 12).pack(side="left")
    def change(v):
        cfg["minutes"] = opts[v]
        app.save()
        if opts[v]:
            app.after(opts[v] * 60000, tick)
    seg = app.seg(r2, list(opts), change)
    seg.set(next(k for k, v in opts.items() if v == cfg.get("minutes", 0)))
    seg.pack(side="left", padx=8)
    refresh()
    if cfg.get("minutes"):
        app.after(cfg["minutes"] * 60000, tick)
