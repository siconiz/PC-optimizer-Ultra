"""Graphics & Cooling: temperatures, fan speeds and fan control (LibreHardwareMonitorLib + PawnIO)."""
import webbrowser
import customtkinter as ctk
from core import sensors
from core.i18n import t
from .theme import ACCENT, CARD, CARD2, MUTED, WARN, F

def section(app, p):
    body = app.card(p, t("Temperatures and fans"), t("Reads CPU, GPU, motherboard and drive sensors and can control "
                    "fans the motherboard or graphics card lets software control. CPU and motherboard sensors need "
                    "the free PawnIO driver (signed, used by LibreHardwareMonitor and FanControl)."))
    r = app.row(body)
    st = app.label(r, "", 13)
    st.pack(side="left")
    def status():
        v = sensors.pawnio_version()
        st.configure(text=t("PawnIO {v} installed", v=v) if v else t("PawnIO is not installed"),
                     text_color=ACCENT if v else WARN)
        inst.configure(text=t("Reinstall PawnIO") if v else t("Install PawnIO"))
    def install():
        if app.ask(t("Install PawnIO"), t("The official PawnIO installer will open. PawnIO is open source (GPL-2.0, "
                   "source: {url}). Continue?", url=sensors.PAWNIO_SRC)):
            def done(_):
                status()
                app.set_sensors(False)
                app.set_sensors(True)  # reload so the library picks up the driver
            app.bg(sensors.install_pawnio, done)
    inst = app.button(r, "", install, primary=False)
    inst.pack(side="right")
    app.button(r, t("Source code"), lambda: webbrowser.open(sensors.PAWNIO_SRC), primary=False,
               width=110).pack(side="right", padx=6)
    status()
    def toggle(on):
        app.cfg["sensors"] = on
        app.save()
        app.set_sensors(on)
    app.switch_row(body, t("Read sensors"), t("Uses about 60 MB of RAM while the app is open."),
                   app.cfg.get("sensors", True), toggle)
    temps = app.table(body, [("hw", t("Device")), ("name", t("Sensor")), ("v", t("Temperature"))], (300, 260, 120), 7,
                      {"hot": WARN})
    fans = app.table(body, [("hw", t("Device")), ("name", t("Fan")), ("v", t("Speed"))], (300, 260, 120), 4)
    msg = app.label(body, "", 12, muted=True, wrap=820)
    msg.pack(anchor="w", pady=(6, 0))
    def tick():
        hw = app.hw
        if not hw:
            msg.configure(text=t("Sensors are off."))
            return
        if hw.error and not hw.snapshot:
            msg.configure(text=t("Sensors could not start: {e}", e=hw.error))
            return
        for tree, kind, unit in ((temps, "Temperature", "°C"), (fans, "Fan", " RPM")):
            tree.delete(*tree.get_children())
            for s in hw.snapshot:
                if s["type"] == kind and s["value"] is not None:
                    hot = kind == "Temperature" and s["value"] >= 90
                    tree.insert("", "end", tags=("hot",) if hot else (), values=(s["hw"], s["name"], f"{s['value']:g}{unit}"))
        msg.configure(text="" if hw.snapshot else t("Starting..."))
    app.every(2000, tick, temps, "Graphics & Cooling")
    _control(app, p)

def _control(app, p):
    body = app.card(p, t("Fan control"), t("Pick a fan, then Auto (BIOS / driver decides), a fixed speed, or a curve "
                    "that follows a temperature. Above 90°C every fan the app controls goes to 100%, and all fans go "
                    "back to Auto when the app closes. Laptop fans are usually locked by the maker: use its app."))
    rules = app.cfg.setdefault("fans", {})
    tree = app.table(body, [("hw", t("Device")), ("name", t("Fan")), ("v", t("Now")), ("mode", t("Mode"))],
                     (280, 220, 90, 160), 4)
    form = ctk.CTkFrame(body, fg_color=CARD2, corner_radius=10)
    state = {"sid": None}
    modes = {"auto": t("Auto"), "fixed": t("Fixed"), "curve": t("Curve")}
    def describe(r):
        if r["mode"] == "fixed":
            return f"{t('Fixed')} {r['value']:.0f}%"
        if r["mode"] == "curve":
            return f"{t('Curve')} {r['t1']}°C→{r['p1']}% … {r['t2']}°C→{r['p2']}%"
        return t("Auto")
    def fill():
        hw = app.hw
        if not hw:
            return
        sel = tree.selection()
        tree.delete(*tree.get_children())
        for s in hw.snapshot:
            if s["type"] == "Control":
                tree.insert("", "end", iid=s["id"], values=(s["hw"], s["name"], f"{s['value'] or 0:.0f}%",
                                                            describe(rules.get(s["id"], {"mode": "auto"}))))
        if sel and tree.exists(sel[0]):
            tree.selection_set(sel[0])
    app.every(2500, fill, tree, "Graphics & Cooling")
    # editor
    r1 = app.row(form, (10, 4))
    seg = app.seg(r1, list(modes.values()))
    seg.pack(side="left", padx=10)
    val = ctk.CTkSlider(r1, from_=0, to=100, width=220)
    val_lbl = app.label(r1, "", 13)
    val.configure(command=lambda v: val_lbl.configure(text=f"{v:.0f}%"))
    r2 = app.row(form, (4, 10))
    temp_names = {}
    src = ctk.CTkOptionMenu(r2, values=["-"], width=300, height=30, fg_color=CARD, button_color=CARD)
    entries, pairs = {}, []
    for k, unit in (("t1", "°C"), ("p1", "%"), ("t2", "°C"), ("p2", "%")):
        f = ctk.CTkFrame(r2, fg_color="transparent")
        entries[k] = ctk.CTkEntry(f, width=52, height=30)
        entries[k].pack(side="left")
        app.label(f, unit, 12, muted=True).pack(side="left", padx=(2, 6))
        pairs.append(f)
    def layout(mode):
        for w in (val, val_lbl, src, *pairs):
            w.pack_forget()
        if mode == "fixed":
            val.pack(side="left", padx=10)
            val_lbl.pack(side="left")
        elif mode == "curve":
            src.pack(side="left", padx=10)
            for f in pairs:
                f.pack(side="left")
    seg.configure(command=lambda v: layout(next(k for k, n in modes.items() if n == v)))
    def pick(_=None):
        sel = tree.selection()
        if not sel or not app.hw:
            form.pack_forget()
            return
        if sel[0] == state["sid"] and form.winfo_ismapped():
            return  # the 2.5 s refresh re-selects the row: keep what the user is typing
        state["sid"] = sel[0]
        r = rules.get(sel[0], {"mode": "auto", "value": 60, "t1": 40, "p1": 30, "t2": 80, "p2": 100})
        temp_names.clear()
        temp_names.update({f"{s['hw']} - {s['name']}": s["id"] for s in app.hw.temps()})
        src.configure(values=list(temp_names) or ["-"])
        src.set(next((k for k, v in temp_names.items() if v == r.get("sensor")), next(iter(temp_names), "-")))
        val.set(r.get("value", 60))
        val_lbl.configure(text=f"{r.get('value', 60):.0f}%")
        for k, e in entries.items():
            e.delete(0, "end")
            e.insert(0, str(r.get(k, "")))
        seg.set(modes[r["mode"]])
        layout(r["mode"])
        form.pack(fill="x", pady=(8, 0), before=bottom)
    def save():
        sid = state["sid"]
        if not sid:
            return
        mode = next(k for k, n in modes.items() if n == seg.get())
        r = {"mode": mode, "value": round(val.get())}
        if mode == "curve":
            try:
                r.update({k: float(e.get()) for k, e in entries.items()}, sensor=temp_names.get(src.get()))
            except ValueError:
                return app.info(t("Fan control"), t("Enter numbers for the curve."))
            if r["t2"] <= r["t1"] or not r["sensor"]:
                return app.info(t("Fan control"), t("The second temperature must be higher than the first."))
        if mode != "auto" and min(r.get("value", 100), r.get("p1", 100)) < 20:
            if not app.ask(t("Fan control"), t("Below 20% some fans stop completely. Continue?"), warn=True):
                return
        rules[sid] = r
        app.save()
        fill()
    app.button(app.row(form, (0, 10)), t("Apply"), save, width=90).pack(side="left", padx=10)
    tree.bind("<<TreeviewSelect>>", pick)
    def all_auto():
        rules.clear()
        app.save()
        fill()
    bottom = app.row(body, (6, 0))
    app.button(bottom, t("All fans to Auto"), all_auto, primary=False).pack(side="left")
