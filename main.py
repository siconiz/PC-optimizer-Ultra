"""PC Optimizer entry point. Run: python main.py (asks for admin)."""
import ctypes, glob, os, sys
from core import config, i18n
from ui import theme

def ensure_admin():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        argv = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in argv), None, 1)
        sys.exit()

def load_fonts():
    """Fonts from the downloadable font pack, for this process only (FR_PRIVATE)."""
    folder = os.path.join(os.environ.get("LOCALAPPDATA", ""), "PCOptimizer", "fonts")
    for f in glob.glob(os.path.join(folder, "*.otf")) + glob.glob(os.path.join(folder, "*.ttf")):
        ctypes.windll.gdi32.AddFontResourceExW(f, 0x10, 0)

if __name__ == "__main__":
    ensure_admin()
    cfg = config.load()
    if "--after-game-boot" in sys.argv:
        from core import gameboot
        gameboot.after_boot()
    i18n.init(cfg.get("lang", "auto"))
    theme.init(cfg.get("theme", "system"), cfg.get("accent", "green"), cfg.get("surface", "navy"))  # before any UI
    # module reads the colors
    if cfg.get("font"):
        load_fonts()
    from ui import kit
    kit.TIPS["on"] = cfg.get("tooltips", True)
    from ui.app import App
    App(cfg).mainloop()
