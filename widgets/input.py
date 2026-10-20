"""PC Optimizer downloadable widget: mouse and keyboard settings (standard Windows settings, SystemParametersInfo)."""
import ctypes
import customtkinter as ctk
from core.i18n import t

SPI = ctypes.windll.user32.SystemParametersInfoW
SAVE = 0x01 | 0x02  # write to the user profile and tell other apps

class STICKY(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint)]

class FILTER(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint), ("iWaitMSec", ctypes.c_uint),
                ("iDelayMSec", ctypes.c_uint), ("iRepeatMSec", ctypes.c_uint), ("iBounceMSec", ctypes.c_uint)]
HOTKEY = 0x4  # SKF_HOTKEYACTIVE / FKF_HOTKEYACTIVE: the "press Shift 5 times" style shortcut

def _get_int(code):
    v = ctypes.c_uint()
    SPI(code, 0, ctypes.byref(v), 0)
    return v.value

def mouse_speed():
    return _get_int(0x70)

def set_mouse_speed(v):
    SPI(0x71, 0, ctypes.c_void_p(int(v)), SAVE)

def acceleration():
    arr = (ctypes.c_int * 3)()
    SPI(0x03, 0, arr, 0)
    return arr[2] != 0

def set_acceleration(on):
    """'Enhance pointer precision'. Off = raw-like 1:1 movement, which most games prefer. (6, 10, 1) is Windows'
    default when it is on."""
    SPI(0x04, 0, (ctypes.c_int * 3)(*((6, 10, 1) if on else (0, 0, 0))), SAVE)

def set_wheel(lines):
    SPI(0x69, int(lines), None, SAVE)

def set_kb_delay(v):
    SPI(0x17, int(v), None, SAVE)

def set_kb_speed(v):
    SPI(0x0B, int(v), None, SAVE)

def _shortcut(get, set_, cls, on=None):
    s = cls()
    s.cbSize = ctypes.sizeof(cls)
    SPI(get, s.cbSize, ctypes.byref(s), 0)
    if on is None:
        return bool(s.dwFlags & HOTKEY)
    s.dwFlags = s.dwFlags | HOTKEY if on else s.dwFlags & ~HOTKEY
    SPI(set_, s.cbSize, ctypes.byref(s), SAVE)

def build(app, body):
    from ui.theme import ACCENT
    def slider(label, lo, hi, value, fn, tip):
        r = app.row(body, 3)
        app.label(r, label, 13, width=170, anchor="w").pack(side="left")
        val = app.label(r, str(value), 12, muted=True, width=30)
        s = ctk.CTkSlider(r, from_=lo, to=hi, number_of_steps=hi - lo, width=200, progress_color=ACCENT)
        s.set(value)
        s.configure(command=lambda v: val.configure(text=str(int(v))))
        s.bind("<ButtonRelease-1>", lambda e: fn(int(s.get())))
        s.pack(side="left", padx=6)
        val.pack(side="left")
        app.tip(r, tip)
    slider(t("Pointer speed"), 1, 20, mouse_speed(), set_mouse_speed, t("Windows pointer speed (default 10). Game "
           "sensitivity is separate; for games keep 10 and change it in the game."))
    slider(t("Lines per scroll"), 1, 20, _get_int(0x68), set_wheel, t("Lines the mouse wheel scrolls at once (default 3)."))
    slider(t("Key repeat delay"), 0, 3, _get_int(0x16), set_kb_delay, t("Wait before a held key repeats: 0 is the "
           "shortest (about 250 ms), 3 the longest (about 1 s)."))
    slider(t("Key repeat speed"), 0, 31, _get_int(0x0A), set_kb_speed, t("How fast a held key repeats: 0 is about 2.5 "
           "times a second, 31 about 30."))
    app.switch_row(body, t("Enhance pointer precision (mouse acceleration)"), t("Off gives the same movement for the "
                   "same hand motion, which most games and players prefer."), acceleration(), set_acceleration)
    app.switch_row(body, t("Sticky Keys shortcut (press Shift 5 times)"), t("Turning the shortcut off stops the Sticky "
                   "Keys prompt from popping up during games. Sticky Keys itself stays available in Settings."),
                   _shortcut(0x3A, 0x3B, STICKY), lambda on: _shortcut(0x3A, 0x3B, STICKY, on))
    app.switch_row(body, t("Filter Keys shortcut (hold right Shift 8 s)"), t("Same as above for the Filter Keys prompt."),
                   _shortcut(0x32, 0x33, FILTER), lambda on: _shortcut(0x32, 0x33, FILTER, on))
    app.label(body, t("Polling rate (Hz) and DPI are set in the mouse's own software, not in Windows."), 11,
              muted=True).pack(anchor="w", pady=(6, 0))
