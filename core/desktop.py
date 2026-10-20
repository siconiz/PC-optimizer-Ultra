"""Notifications (global, per app, Windows tips) and visual effects (animations, transparency, shadows)."""
import ctypes, subprocess, winreg
from .reg import HKCU, get, set_value

PUSH = r"Software\Microsoft\Windows\CurrentVersion\PushNotifications"
NOTIF = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
CDM = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
TIPS = {"Tips and suggestions": (CDM, "SubscribedContent-338389Enabled"),
        "Windows welcome experience": (CDM, "SubscribedContent-310093Enabled"),
        "Suggest ways to finish setting up": (r"Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement",
                                              "ScoobeSystemSettingEnabled")}
PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
ADVANCED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
VFX = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
NOWIN = 0x08000000

# ---- notifications ----
def notifications_on():
    return get(HKCU, PUSH, "ToastEnabled", 1) != 0

def set_notifications(on):
    set_value(HKCU, PUSH, "ToastEnabled", int(on))
    set_value(HKCU, NOTIF, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", int(on))
    subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Service WpnUserService* | Restart-Service -Force"],
                   capture_output=True, creationflags=NOWIN)  # applies it without signing out

def app_notifications():
    """[(app id, readable name, enabled)] for apps that have sent notifications before."""
    out = []
    try:
        with winreg.OpenKey(HKCU, NOTIF) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                aid = winreg.EnumKey(k, i)
                name = aid.split("\\")[-1].split("!")[0].split("_")[0]  # "Microsoft.WindowsStore_8wekyb3d8bbwe!App"
                out.append((aid, name, get(HKCU, f"{NOTIF}\\{aid}", "Enabled", 1) != 0))
    except OSError:
        pass
    return sorted(out, key=lambda x: x[1].lower())

def set_app_notifications(aid, on):
    set_value(HKCU, f"{NOTIF}\\{aid}", "Enabled", int(on))

def tip_on(name):
    return get(HKCU, *TIPS[name], 1) != 0

def set_tip(name, on):
    set_value(HKCU, *TIPS[name], int(on))

# ---- visual effects ----
SPI = ctypes.windll.user32.SystemParametersInfoW if hasattr(ctypes, "windll") else None
GET_ANIM, SET_ANIM = 0x1042, 0x1043          # client area animations ("Animation effects" in Settings)
GET_SHADOW, SET_SHADOW = 0x1024, 0x1025
SET_MENU, SET_TOOLTIP, SET_COMBO = 0x1003, 0x1017, 0x1005
SPI_GETANIMATION, SPI_SETANIMATION = 0x48, 0x49  # minimize / maximize animation
SAVE = 0x01 | 0x02                           # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE

class ANIMATIONINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("iMinAnimate", ctypes.c_int)]

def _get(code):
    v = ctypes.c_int()
    SPI(code, 0, ctypes.byref(v), 0)
    return bool(v.value)

def effects():
    return {"Animations": _get(GET_ANIM), "Shadows": _get(GET_SHADOW),
            "Transparency": get(HKCU, PERSONALIZE, "EnableTransparency", 1) != 0}

def set_effect(name, on):
    set_value(HKCU, VFX, "VisualFXSetting", 3)  # 3 = Custom in Performance Options
    if name == "Animations":
        for code in (SET_ANIM, SET_MENU, SET_TOOLTIP, SET_COMBO):
            SPI(code, 0, ctypes.c_void_p(int(on)), SAVE)
        ai = ANIMATIONINFO(ctypes.sizeof(ANIMATIONINFO), int(on))
        SPI(SPI_SETANIMATION, ctypes.sizeof(ai), ctypes.byref(ai), SAVE)
        set_value(HKCU, ADVANCED, "TaskbarAnimations", int(on))
    elif name == "Shadows":
        SPI(SET_SHADOW, 0, ctypes.c_void_p(int(on)), SAVE)
    elif name == "Transparency":
        set_value(HKCU, PERSONALIZE, "EnableTransparency", int(on))

def open_performance_options():
    subprocess.Popen(["SystemPropertiesPerformance.exe"])
