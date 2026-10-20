"""PC Optimizer downloadable widget: audio output devices with their type, app volumes and microphone mute."""
import customtkinter as ctk
from core.i18n import t

FORM_FACTOR = "{1DA5D803-D492-4EDD-8C23-E0C0FFEE7F0E} 0"   # PKEY_AudioEndpoint_FormFactor
ENUMERATOR = "{A45C254E-DF1C-4EFD-8020-67D146A850E0} 24"   # PKEY_Device_EnumeratorName (BTHENUM = Bluetooth)
# EndpointFormFactor values (mmdeviceapi.h)
KINDS = {1: ("Speakers", "speakers"), 3: ("Headphones", "headphone"), 5: ("Headset", "headset"),
         8: ("Optical (S/PDIF)", "speakers"), 9: ("Monitor speakers (HDMI/DP)", "monitor"), 2: ("Line out", "speakers")}

def kind(dev):
    """('Headset', icon, bluetooth?) from Windows' form factor; sound bars have no own type, so the name decides."""
    name = (dev.FriendlyName or "").lower()
    bt = "bth" in str(dev.properties.get(ENUMERATOR, "")).lower() or "bluetooth" in name
    if "soundbar" in name or "sound bar" in name:
        return "Sound bar", "speakers", bt
    label, glyph = KINDS.get(dev.properties.get(FORM_FACTOR), ("Audio device", "volume"))
    return label, glyph, bt

def outputs():
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import DEVICE_STATE, EDataFlow
    return AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)

def default_id():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().id

def set_default(dev_id):
    """Uses the same unofficial Windows interface as EarTrumpet/SoundSwitch; may stop working after updates."""
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import ERole
    AudioUtilities.SetDefaultDevice(dev_id, [ERole.eConsole, ERole.eMultimedia, ERole.eCommunications])

def mic_volume():
    import comtypes
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    mic = AudioUtilities.GetMicrophone()
    return mic.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)

def build(app, body):
    from ui.theme import ACCENT, CARD2, MUTED, TEXT, IF, F, icon
    box = ctk.CTkFrame(body, fg_color="transparent", height=1)
    box.pack(fill="x")
    apps = app.scroll_box(body, 180) if hasattr(app, "scroll_box") else ctk.CTkFrame(body, fg_color="transparent", height=1)
    def refresh():
        for w in box.winfo_children() + apps.winfo_children():
            w.destroy()
        try:
            cur = default_id()
            devs = outputs()
        except Exception as e:
            msg = t("No audio output device found.") if "not found" in str(e).lower() or "0x80070490" in str(e) \
                else t("Audio devices could not be read: {e}", e=e)
            app.label(box, msg, 12, muted=True, wrap=420).pack(anchor="w")
            return
        app.label(box, t("Output"), 12, muted=True).pack(anchor="w")
        for d in devs:
            label, glyph, bt = kind(d)
            on = d.id == cur
            r = ctk.CTkFrame(box, fg_color=CARD2 if on else "transparent", corner_radius=8, height=1)
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=icon(glyph), font=IF(16), text_color=ACCENT if on else TEXT, width=28).pack(side="left", padx=(6, 4))
            txt = t(label) + (" · Bluetooth" if bt else "") + ("  ✓ " + t("in use") if on else "")
            app.label(r, d.FriendlyName or "-", 13, bold=on).pack(side="left")
            app.label(r, "  " + txt, 11, muted=True).pack(side="left")
            if not on:
                def use(i=d.id):
                    try:
                        set_default(i)
                    except Exception:
                        __import__("os").startfile("ms-settings:sound")  # fall back to Windows sound settings
                    refresh()
                app.button(r, t("Use"), use, primary=False, width=60).pack(side="right", padx=4, pady=2)
            app.tip(r, t("Type comes from Windows (speakers, headphones, headset, HDMI/DisplayPort monitor, optical). "
                         "Sound bars have no type of their own and are recognised by name."))
        try:
            mv = mic_volume()
            row = app.row(box, (6, 0))
            ctk.CTkLabel(row, text=icon("mic"), font=IF(16), text_color=TEXT, width=28).pack(side="left", padx=(6, 4))
            app.label(row, t("Microphone"), 13).pack(side="left")
            sw = ctk.CTkSwitch(row, text=t("Muted"), progress_color=ACCENT, font=F(12))
            sw.pack(side="right")
            sw.select() if mv.GetMute() else sw.deselect()
            sw.configure(command=lambda: mv.SetMute(int(sw.get()), None))
        except Exception:
            pass
        sessions(app, apps)
    def sessions(app, parent):
        from pycaw.pycaw import AudioUtilities
        rows = [s for s in AudioUtilities.GetAllSessions() if s.Process]
        if rows:
            app.label(parent, t("App volume"), 12, muted=True).pack(anchor="w", pady=(8, 0))
        for s in rows[:8]:
            r = app.row(parent, 1)
            app.label(r, s.Process.name().replace(".exe", ""), 12, width=140, anchor="w").pack(side="left")
            vol = s.SimpleAudioVolume
            sl = ctk.CTkSlider(r, from_=0, to=100, width=180, progress_color=ACCENT)
            sl.set(vol.GetMasterVolume() * 100)
            sl.configure(command=lambda v, x=vol: x.SetMasterVolume(v / 100, None))
            sl.pack(side="left", padx=8)
        if hasattr(app, "fit_scroll"):
            app.fit_scroll(parent)
    r = app.row(body, (6, 0))
    app.button(r, t("Refresh"), refresh, primary=False, width=80).pack(side="left")
    app.button(r, t("Sound settings"), lambda: __import__("os").startfile("ms-settings:sound"), primary=False).pack(side="left", padx=6)
    refresh()
