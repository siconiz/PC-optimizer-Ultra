"""PC Optimizer downloadable widget: display brightness and refresh rate for every monitor."""
import ctypes, os
from ctypes import wintypes
import customtkinter as ctk
import win32api, win32con
from core.i18n import t

class PHYS(ctypes.Structure):
    _fields_ = [("h", wintypes.HANDLE), ("desc", ctypes.c_wchar * 128)]

def monitors():
    """[(device name, HMONITOR, physical monitor handles)]"""
    out, dx = [], ctypes.windll.dxva2
    for hmon, _, _ in win32api.EnumDisplayMonitors():
        dev = win32api.GetMonitorInfo(hmon)["Device"]
        n = wintypes.DWORD()
        phys = []
        if dx.GetNumberOfPhysicalMonitorsFromHMONITOR(wintypes.HANDLE(int(hmon)), ctypes.byref(n)) and n.value:
            arr = (PHYS * n.value)()
            if dx.GetPhysicalMonitorsFromHMONITOR(wintypes.HANDLE(int(hmon)), n.value, arr):
                phys = list(arr)
        out.append((dev, phys))
    return out

def get_brightness(phys):
    lo, cur, hi = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
    for p in phys:  # DDC/CI (external monitors)
        if ctypes.windll.dxva2.GetMonitorBrightness(wintypes.HANDLE(p.h), ctypes.byref(lo), ctypes.byref(cur), ctypes.byref(hi)):
            return ("ddc", wintypes.HANDLE(p.h), lo.value, hi.value), cur.value
    try:  # built-in laptop panel
        import wmi
        b = wmi.WMI(namespace="wmi").WmiMonitorBrightness()[0].CurrentBrightness
        return ("wmi", None, 0, 100), b
    except Exception:
        return None, None

def set_brightness(ctl, value):
    kind, h, lo, hi = ctl
    if kind == "ddc":
        ctypes.windll.dxva2.SetMonitorBrightness(h, int(max(lo, min(hi, value))))
    else:
        import wmi
        wmi.WMI(namespace="wmi").WmiMonitorBrightnessMethods()[0].WmiSetBrightness(0, int(value))

def rates(dev):
    cur = win32api.EnumDisplaySettings(dev, win32con.ENUM_CURRENT_SETTINGS)
    hz = set()
    i = 0
    while True:
        try:
            m = win32api.EnumDisplaySettings(dev, i)
        except Exception:
            break
        if (m.PelsWidth, m.PelsHeight) == (cur.PelsWidth, cur.PelsHeight):
            hz.add(m.DisplayFrequency)
        i += 1
    return cur, sorted(hz)

def set_rate(dev, hz):
    dm = win32api.EnumDisplaySettings(dev, win32con.ENUM_CURRENT_SETTINGS)
    dm.DisplayFrequency, dm.Fields = hz, win32con.DM_DISPLAYFREQUENCY
    win32api.ChangeDisplaySettingsEx(dev, dm, win32con.CDS_UPDATEREGISTRY)

def build(app, body):
    for dev, phys in monitors():
        r = app.row(body, 4)
        cur, hz = rates(dev)
        app.label(r, f"{dev.split(chr(92))[-1]}  {cur.PelsWidth}x{cur.PelsHeight}", 13,
                  width=190, anchor="w").pack(side="left")
        ctl, b = get_brightness(phys)
        if ctl:
            s = ctk.CTkSlider(r, from_=ctl[2], to=ctl[3], width=220)
            s.set(b)
            s.bind("<ButtonRelease-1>", lambda e, c=ctl, w=s: set_brightness(c, w.get()))
            s.pack(side="left", padx=8)
        else:
            app.label(r, t("Brightness not adjustable (no DDC/CI)"), 12, muted=True).pack(side="left", padx=8)
        if len(hz) > 1:
            seg = app.seg(r, [f"{h} Hz" for h in hz], lambda v, d=dev: set_rate(d, int(v.split()[0])))
            seg.set(f"{cur.DisplayFrequency} Hz")
            seg.pack(side="right")
    r = app.row(body, (8, 0))
    app.button(r, t("Night light"), lambda: os.startfile("ms-settings:nightlight"), primary=False).pack(side="left")
    app.button(r, t("HDR and display settings"), lambda: os.startfile("ms-settings:display"),
               primary=False).pack(side="left", padx=6)
