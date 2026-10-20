"""Colors, fonts and icons. init() runs before any UI module imports the color names."""
import os
import customtkinter as ctk

# The original PC Optimizer look: deep navy surfaces, green accent, rounded cards
DARK = dict(BG="#0e1116", SIDE="#141922", CARD="#1a202b", CARD2="#222a37", HOVER2="#2c3646", TEXT="#e7ebf2",
            MUTED="#8b95a7", SEL="#24533a", SEL_H="#2c6446", WARN="#f2b84b", ACCENT="#3ddc84", ACCENT_H="#2fb36a",
            ON_ACCENT="#0b0f14", BORDER="#222a37", TABLE="#141922", SEG_SEL="#24533a")
LIGHT = dict(BG="#eef1f5", SIDE="#e4e8ee", CARD="#ffffff", CARD2="#edf0f4", HOVER2="#dfe4eb", TEXT="#141922",
             MUTED="#5b6577", SEL="#cfeedd", SEL_H="#bfe6d1", WARN="#a86a00", ACCENT="#1fa863", ACCENT_H="#1a9156",
             ON_ACCENT="#ffffff", BORDER="#dfe4eb", TABLE="#ffffff", SEG_SEL="#cfeedd")
R_CARD, R = 14, 8  # corner radius of cards / of buttons, inputs and tiles
BG = SIDE = CARD = CARD2 = HOVER2 = TEXT = MUTED = SEL = SEL_H = WARN = ACCENT = ACCENT_H = ON_ACCENT = BORDER = TABLE = \
    SEG_SEL = ""
FONT = ["Segoe UI"]
ICON_FONT = [None]  # "Segoe Fluent Icons" (Windows 11) or "Segoe MDL2 Assets" (Windows 10)
MODE = ["dark"]
# Code points from Microsoft's WinUI Gallery icon list (Segoe Fluent Icons)
ICONS = {"home": "", "apps": "", "robot": "", "cpu": "", "game": "",
         "diag": "", "broom": "", "settings": "", "info": "", "overlay": "",
         "add": "", "more": "", "close": "", "move": "", "folder": "",
         "delete": "", "play": "", "refresh": "", "speakers": "", "headphone": "",
         "headset": "", "monitor": "", "volume": "", "mic": "", "battery": "",
         "charging": "", "drive": "", "wifi": "", "network": "", "clock": "",
         "calendar": "", "mouse": "", "keyboard": "", "photo": "", "font": "",
         "brightness": "", "download": "", "speed": "", "shield": "", "help": "",
         "chevron_down": "", "chevron_right": "", "power": "", "equalizer": ""}

def _system_dark():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return True

def _shade(color, f):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * f))) for c in (r, g, b))

def init(mode="system"):
    """mode: 'system', 'light' or 'dark'. Restart the app to switch."""
    dark = _system_dark() if mode == "system" else mode == "dark"
    MODE[0] = "dark" if dark else "light"
    pal = dict(DARK if dark else LIGHT)
    globals().update(pal)
    ctk.set_appearance_mode(MODE[0])
    tm = ctk.ThemeManager.theme  # green accent also for widgets that do not set their colors themselves
    a, h = [pal["ACCENT"]] * 2, [pal["ACCENT_H"]] * 2
    for name, keys in (("CTkSlider", ("button_color", "progress_color")), ("CTkSwitch", ("progress_color",)),
                       ("CTkCheckBox", ("fg_color",)), ("CTkProgressBar", ("progress_color",)),
                       ("CTkRadioButton", ("fg_color",)), ("CTkButton", ("fg_color",))):
        for k in keys:
            tm[name][k] = a
    tm["CTkSlider"]["button_hover_color"] = tm["CTkCheckBox"]["hover_color"] = tm["CTkButton"]["hover_color"] = h
    tm["CTkButton"]["text_color"] = [pal["ON_ACCENT"]] * 2

def pick_fonts(root, lang, extra=None):
    """Called once the Tk root exists: Segoe UI, Malgun Gothic for Korean,
    or a downloaded font (extra) if the user chose one."""
    from tkinter import font
    fams = set(font.families(root))
    if extra and extra in fams:
        FONT[0] = extra
    elif lang == "ko":
        FONT[0] = "Malgun Gothic" if "Malgun Gothic" in fams else "Segoe UI"
    else:
        FONT[0] = "Segoe UI"
    ICON_FONT[0] = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in fams), None)

def set_font(lang):  # kept for main.py before the root exists
    FONT[0] = "Malgun Gothic" if lang == "ko" else "Segoe UI"

def F(size, weight="normal"):
    return ctk.CTkFont(FONT[0], size, weight)

def icon(name):
    """Glyph for an icon name, or '' when no icon font is installed."""
    return ICONS.get(name, "") if ICON_FONT[0] else ""

def IF(size=16):
    return ctk.CTkFont(ICON_FONT[0] or FONT[0], size)

init("dark")  # defaults until main.py calls init() with the user's choice
