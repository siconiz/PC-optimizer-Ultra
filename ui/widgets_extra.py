"""Built-in dashboard widgets added in 1.0: clock, network, drive speed, free space, battery."""
import calendar, datetime, re
import customtkinter as ctk
import psutil
from core import battery, disk, net
from core.i18n import t
from .theme import ACCENT, CARD2, MUTED, ON_ACCENT, TEXT, WARN, F, IF, icon

def _bar(parent, frac, color=ACCENT, h=8):
    b = ctk.CTkProgressBar(parent, height=h, progress_color=color, fg_color=CARD2, corner_radius=8)
    b.set(max(0.0, min(1.0, frac)))
    return b

def clock_widget(app, body):
    now = ctk.CTkLabel(body, text="", font=F(26, "bold"), text_color=TEXT)
    now.pack(anchor="w")
    day = app.label(body, "", 12, muted=True)
    day.pack(anchor="w")
    cal = ctk.CTkFrame(body, fg_color="transparent", height=1)
    cal.pack(anchor="w", pady=(6, 0))
    names = [t("Mon"), t("Tue"), t("Wed"), t("Thu"), t("Fri"), t("Sat"), t("Sun")]
    state = {"day": None}
    def draw(today):
        import tkinter as tk
        from .theme import CARD, FONT
        for w in cal.winfo_children():
            w.destroy()
        for i, n in enumerate(names):
            tk.Label(cal, text=n, font=(FONT[0], 8), fg=MUTED, bg=CARD, width=3).grid(row=0, column=i)
        for r, week in enumerate(calendar.monthcalendar(today.year, today.month), 1):
            for c, d in enumerate(week):
                if d:  # plain tk labels: no extra padding, so the month fits a small widget
                    on = d == today.day
                    tk.Label(cal, text=str(d), font=(FONT[0], 8, "bold" if on else "normal"), width=3,
                             fg=ON_ACCENT if on else TEXT, bg=ACCENT if on else CARD).grid(row=r, column=c)
    def tick():
        n = datetime.datetime.now()
        now.configure(text=n.strftime("%H:%M"))
        day.configure(text=t("{y}-{m:02d}-{d:02d} ({w})", y=n.year, m=n.month, d=n.day, w=names[n.weekday()]))
        if state["day"] != n.date():
            state["day"] = n.date()
            draw(n.date())
    app.every(1000, tick, now, "Dashboard")

def network_widget(app, body):
    info = app.label(body, t("Checking..."), 12, wrap=520)
    info.pack(anchor="w")
    ping = app.label(body, "", 12, muted=True)
    ping.pack(anchor="w")
    def links():
        w, a = net.wifi(), net.adapters()
        parts = [f"{x['ssid']}  {x['signal']}% ({x['dbm']} dBm)  {x['rx']} Mbps" for x in w]
        parts += [f"{x['name']}  {x['mbps']} Mbps" for x in a if not any(x["name"] in y["adapter"] for y in w)]
        return " · ".join(parts) or t("No active connection.")
    def show_ping(r):
        if r["avg"] is None:
            ping.configure(text=t("Ping: no reply"), text_color=WARN)
        else:
            ping.configure(text=t("Ping {avg} ms, jitter {j} ms, loss {loss}%", avg=r["avg"], j=r["jitter"],
                                  loss=r["loss"]), text_color=WARN if r["avg"] > 80 or r["loss"] else MUTED)
    def tick():
        app.bg(links, lambda s: info.configure(text=s), lambda m: None)
        app.bg(lambda: net.ping("1.1.1.1", 4), show_ping, lambda m: None)
    app.every(10000, tick, info, "Dashboard")
    app.tip(body.master, t("Wi-Fi signal and link rate, adapter speed, and ping to 1.1.1.1 every 10 seconds."))

def ssd_widget(app, body):
    try:
        drives = disk.drives() or ["C:"]
    except Exception:
        drives = ["C:"]
    r = app.row(body)
    pick = app.seg(r, drives)
    pick.set(drives[0])
    pick.pack(side="left")
    out = ctk.CTkFrame(body, fg_color="transparent", height=1)
    out.pack(fill="x", pady=(6, 0))
    status = app.label(body, t("Press Test. It writes a temporary 512 MB file and reads it back."), 11, muted=True)
    status.pack(anchor="w")
    def show(res):
        for w in out.winfo_children():
            w.destroy()
        top = max(res["seq_read"], res["average"] or 1)
        for label, mb, color in ((t("This drive"), res["seq_read"], ACCENT),
                                 (t("Typical {kind}", kind=t(res["kind"])), res["average"] or 0, MUTED)):
            row = app.row(out, 2)
            app.label(row, label, 12, width=130, anchor="w").pack(side="left")
            _bar(row, mb / top, color).pack(side="left", fill="x", expand=True, padx=6)
            app.label(row, f"{mb} MB/s", 12, width=90, anchor="e").pack(side="right")
        if res["vs_avg"] is not None:
            diff = res["vs_avg"] - 100
            status.configure(text=t("{p}% of a typical {kind} ({d:+d}%). Write {w} MB/s, random 4K {iops} IOPS.",
                                    p=res["vs_avg"], kind=t(res["kind"]), d=diff, w=res["seq_write"],
                                    iops=res["rand_iops"]), text_color=WARN if res["verdict"] == "Slow" else MUTED)
    def run():
        status.configure(text=t("Testing {d} (about 20 seconds)...", d=pick.get()), text_color=MUTED)
        app.bg(lambda: disk.bench(pick.get()), show, lambda m: status.configure(text=m, text_color=WARN))
    app.button(r, t("Test"), run, width=80).pack(side="left", padx=8)
    app.tip(body.master, t("Typical speeds are box speeds of common drives: 7200 rpm HDD about 180 MB/s, SATA SSD "
                           "about 550 MB/s (SATA limit), PCIe 3.0 NVMe about 3,500 MB/s. PCIe 4.0/5.0 drives are "
                           "faster, so above 100% is normal for them."))

def space_widget(app, body):
    box = ctk.CTkFrame(body, fg_color="transparent", height=1)
    box.pack(fill="x")
    def tick():
        for w in box.winfo_children():
            w.destroy()
        for p in psutil.disk_partitions():
            if not p.fstype or "cdrom" in p.opts:
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
            except OSError:
                continue
            low = u.free / u.total < 0.1
            row = app.row(box, 2)
            ctk.CTkLabel(row, text=icon("drive"), font=IF(14), text_color=TEXT, width=22).pack(side="left")
            app.label(row, p.device[:2], 12, width=30).pack(side="left")
            _bar(row, u.percent / 100, WARN if low else ACCENT).pack(side="left", fill="x", expand=True, padx=6)
            app.label(row, t("{f} GB free of {t} GB", f=round(u.free / 2**30), t=round(u.total / 2**30)), 11,
                      muted=not low, width=150, anchor="e").pack(side="right")
            if low:
                app.tip(row, t("Less than 10% free. Windows and SSDs slow down when a drive is nearly full: use the "
                               "Cleanup page."))
    app.every(30000, tick, box, "Dashboard")

def battery_widget(app, body):
    lbl = app.label(body, "", 13, bold=True)
    lbl.pack(anchor="w")
    bar = _bar(body, 0, h=10)
    bar.pack(fill="x", pady=4)
    sub = app.label(body, "", 12, muted=True, wrap=400)
    sub.pack(anchor="w")
    warn = app.label(body, "", 12, wrap=400, text_color=WARN)
    warn.pack(anchor="w")
    tips = app.details(body, t("Which charger to use"))
    for line in battery.CHARGER_TIPS:
        app.label(tips, "•  " + t(line), 12, wrap=400).pack(anchor="w", pady=1)
    app.label(tips, t("The exact wattage your laptop needs is on the maker's spec page (This PC > Details)."), 11,
              muted=True, wrap=400).pack(anchor="w", pady=(4, 0))
    def show(s):
        if not s:
            lbl.configure(text=t("No battery (desktop PC)"))
            return
        bar.set(s["percent"] / 100)
        state = t("Charging") if s["plugged"] else t("On battery")
        lbl.configure(text=f"{s['percent']}%  ·  {state}")
        parts = []
        if s["rate_w"] is not None:
            parts.append(t("{w} W in", w=s["rate_w"]) if s["rate_w"] > 0 else t("{w} W out", w=-s["rate_w"]))
        if s["secs"]:
            parts.append(t("{h} h {m} min left", h=s["secs"] // 3600, m=s["secs"] % 3600 // 60))
        if s["wear"] is not None:
            parts.append(t("Battery health {w}% ({f} of {d} Wh)", w=s["wear"], f=s["full_wh"], d=s["design_wh"]))
        sub.configure(text="  ·  ".join(parts))
        warn.configure(text="\n".join(t(m, w=s["wear"]) for m in battery.advice(s)))
    app.every(5000, lambda: app.bg(battery.status, show, lambda m: None), lbl, "Dashboard")


def _check(app, body, kind):
    """The 검사 button: reads the facts in a worker thread and lists the steps for BIOS. Changes nothing."""
    from core import oc
    res = app.label(body, "", 12, wrap=400)
    def done(lines):
        if res.winfo_exists():
            btn.configure(state="normal", text=t("Check"))
            res.configure(text="\n".join("•  " + x for x in lines), text_color=TEXT)
    def fail(msg):
        if res.winfo_exists():
            btn.configure(state="normal", text=t("Check"))
            res.configure(text=msg, text_color=WARN)
    def run():
        btn.configure(state="disabled", text=t("Checking..."))
        fn = oc.ram_advice if kind == "ram" else oc.cpu_advice
        app.bg(lambda: fn(oc.facts()), done, fail)
    btn = app.button(body, t("Check"), run, primary=False, width=90)
    btn.pack(anchor="w", pady=(8, 0))
    res.pack(anchor="w", pady=(6, 0))

# ---------- read-only overclock status (nothing here changes a setting) ----------
def ram_oc_widget(app, body):
    lbl = app.label(body, "", 13, bold=True)
    lbl.pack(anchor="w")
    sub = app.label(body, "", 12, muted=True, wrap=400)
    sub.pack(anchor="w", pady=(4, 0))
    def tick():
        from core import hardware
        mods = app.cached("ram_speeds", hardware.ram_speeds, [])
        if not mods:
            lbl.configure(text=t("No memory information"))
            return
        running = min(m["running"] for m in mods)
        reported = max(m["rated"] for m in mods)
        lbl.configure(text=t("Running at {mhz} MHz", mhz=running))
        if reported and running > reported:
            note = t("Faster than the speed the module reports: an XMP/EXPO profile or a manual overclock is on.")
        elif reported and running < reported:
            note = t("Slower than the module reports: the profile is off, or the BIOS limits the speed.")
        else:
            note = t("Same as the module reports: no profile is on, or the module's base speed is its rated speed.")
        parts = sorted({m["part"] for m in mods if m["part"]})
        sub.configure(text=note + ("  " + t("Module: {part}", part=", ".join(parts)) if parts else ""))
    _check(app, body, "ram")
    app.every(3000, tick, lbl, "Dashboard")

_UNLOCKED = re.compile(r"\d{4,5}(KF|K|X3D|XE|X)\b")   # e.g. 14700K, 13900KF, 7800X3D, 7950X

def cpu_oc_widget(app, body):
    name = app.label(body, "", 13, bold=True, wrap=400)
    name.pack(anchor="w")
    clock = app.label(body, "", 13)
    clock.pack(anchor="w", pady=(6, 0))
    sub = app.label(body, "", 12, muted=True, wrap=400)
    sub.pack(anchor="w", pady=(4, 0))
    def tick():
        from core import hardware
        model, rated = app.cached("cpu_name", hardware.cpu_name, ("", 0))
        if not model:
            name.configure(text=t("No processor information"))
            return
        unlocked = bool(_UNLOCKED.search(model))
        name.configure(text=model)
        mhz = app.hw.cpu_clock() if app.hw else None
        now = t("Average core clock {mhz} MHz", mhz=mhz) if mhz else t("Clock sensor is off (Sensors setting)")
        clock.configure(text=now + (t("  ·  rated {mhz} MHz", mhz=rated) if rated else ""))
        if unlocked:
            hint = t("Unlocked model (K, KF, X). Intel XTU changes the multiplier only on a Z-series chipset; "
                     "AMD uses Ryzen Master. This app does not change clocks.")
        else:
            hint = t("Locked model: the multiplier cannot be raised. The clock still rises above the rated speed "
                     "on its own (boost).")
        sub.configure(text=hint)
    _check(app, body, "cpu")
    app.every(2000, tick, name, "Dashboard")
