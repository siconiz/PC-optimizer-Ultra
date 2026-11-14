"""Diagnostics page: network, drives (health + speed), temperatures."""
import customtkinter as ctk
from core import disk, gpuinfo, net, sensors
from core.i18n import t
from .theme import ACCENT, CARD, CARD2, HOVER2, MUTED, ON_ACCENT, TEXT, WARN

def page(app, p):
    _network(app, p)
    _drives(app, p)
    _partitions(app, p)
    _temps(app, p)

def _verdict_ping(r):
    if r["avg"] is None:
        return t("No reply. Check the connection or the firewall."), WARN
    bad = [t("high latency") if r["avg"] > 80 else "", t("unstable (jitter)") if r["jitter"] > 20 else "",
           t("packet loss") if r["loss"] > 1 else ""]
    bad = [b for b in bad if b]
    return (t("Problems: {p}", p=", ".join(bad)), WARN) if bad else (t("Good for online games."), ACCENT)

def _network(app, p):
    body = app.card(p, t("Network"), t("Wi-Fi signal and link speed, ping and packet loss, DNS response time and an "
                                       "internet speed test (Cloudflare)."))
    info = app.label(body, t("Checking..."), 13, wrap=820)
    info.pack(anchor="w")
    out = app.label(body, "", 13, wrap=820)
    out.pack(anchor="w", pady=(6, 0))
    def show_links(res):
        wifi, ads = res
        lines = [t("Wi-Fi {ssid}: signal {s}% ({dbm} dBm), link {rx} / {tx} Mbps, {std}", ssid=w["ssid"], s=w["signal"],
                   dbm=w["dbm"], rx=w["rx"], tx=w["tx"], std=w["standard"]) for w in wifi]
        lines += [t("{name}: {mbps} Mbps link", name=a["name"], mbps=a["mbps"]) for a in ads]
        if any(w["signal"] < 50 for w in wifi):
            lines.append(t("The Wi-Fi signal is weak: move closer to the router, use 5 GHz or a cable for games."))
        info.configure(text="\n".join(lines) or t("No active connection."))
    app.bg(lambda: (net.wifi(), net.adapters()), show_links, lambda m: info.configure(text=m))
    r = app.row(body, (8, 0))
    def run(fn, fmt):
        out.configure(text=t("Working..."), text_color=MUTED)
        app.bg(fn, lambda res: out.configure(**fmt(res)), lambda m: out.configure(text=m, text_color=WARN))
    def fmt_ping(r):
        msg, color = _verdict_ping(r)
        if r["avg"] is None:
            return {"text": msg, "text_color": color}
        return {"text": t("Ping {avg} ms (min {min}, max {max}), jitter {j} ms, loss {loss}%. ", avg=r["avg"],
                          min=r["min"], max=r["max"], j=r["jitter"], loss=r["loss"]) + msg, "text_color": color}
    def fmt_dns(r):
        cur, best = r.get("Current"), min((v, k) for k, v in r.items() if v is not None)
        text = "  ".join(f"{t(k)}: {v} ms" if v is not None else f"{t(k)}: -" for k, v in r.items())
        if cur and best[1] != "Current" and cur > best[0] * 1.5 + 10:
            text += "\n" + t("{name} answers faster than your current DNS. You can change DNS in Windows Settings "
                             "> Network.", name=best[1])
        return {"text": text, "text_color": TEXT}
    def fmt_speed(r):
        return {"text": t("Download {d} Mbps, upload {u} Mbps, latency {p} ms (Cloudflare, 4 connections)",
                          d=r["down"], u=r["up"], p=r["ping"]), "text_color": ACCENT}
    app.button(r, t("Ping test"), lambda: run(net.ping, fmt_ping)).pack(side="left")
    app.button(r, t("DNS test"), lambda: run(net.dns_test, fmt_dns), primary=False).pack(side="left", padx=6)
    app.button(r, t("Speed test"), lambda: (run(net.speed_test, fmt_speed),
               out.configure(text=t("Measuring for about 20 seconds..."))), primary=False).pack(side="left")
    app.button(r, t("Network settings"), lambda: __import__("os").startfile("ms-settings:network"),
               primary=False).pack(side="right")

def _drives(app, p):
    body = app.card(p, t("Drives"), t("Health, power-on time and bad sector counts come from the drive's own SMART data. The "
                    "speed test writes a temporary file and reads it back without the Windows cache. The surface scan "
                    "reads every sector without writing."))
    tree = app.table(body, [("name", t("Drive")), ("type", t("Type")), ("size", t("Size (GB)")), ("health", t("Health")),
                            ("temp", t("Temperature")), ("wear", t("Wear")), ("hours", t("Power-on time")),
                            ("sectors", t("Bad sectors"))],
                     (210, 100, 70, 80, 90, 60, 150, 130), 4, {"bad": WARN})
    note = app.label(body, "", 12, muted=True, wrap=880)
    def fill(ds):
        tree.delete(*tree.get_children())
        lines = []
        for d in ds:
            sec = d["sectors"]
            bad_sec = sum(sec.values()) if sec else 0
            bad = d["health"] != "Healthy" or (d["wear"] or 0) >= 80 or d["errors"] or bad_sec
            hours = t("{h} h ({d} days)", h=f"{d['hours']:,}", d=round(d["hours"] / 24)) if d["hours"] else "-"
            tree.insert("", "end", tags=("bad",) if bad else (), values=(
                d["name"], f"{d['media']} / {d['bus']}", d["size_gb"], t(d["health"]),
                f"{d['temp']}°C" if d["temp"] else "-", f"{d['wear']}%" if d["wear"] is not None else "-", hours,
                (str(bad_sec) if bad_sec else t("None")) if sec is not None else t("Not reported")))
            if sec and bad_sec:
                lines.append(t("{name}: reallocated {r}, pending {p}, uncorrectable {u}. Back up this drive now; the "
                               "number rising over time means it is failing.", name=d["name"], r=sec.get(5, 0),
                               p=sec.get(197, 0), u=sec.get(198, 0)))
            if d["errors"]:
                lines.append(t("{name}: {n} read/write errors the drive could not correct.", name=d["name"], n=d["errors"]))
            if d["cycles"]:
                lines.append(t("{name}: turned on {n} times.", name=d["name"], n=f"{d['cycles']:,}"))
        lines.append(t("'Not reported' is normal for most NVMe drives: they report errors in the Health and error "
                       "counts instead. Run the surface scan below to read every sector."))
        note.configure(text="\n".join(lines))
        _scan(app, body, ds)
    note.pack(anchor="w", pady=(6, 0))
    app.bg(disk.health, fill, lambda m: note.configure(text=m, text_color=WARN))
    r = app.row(body, (8, 0))
    try:
        drives = disk.drives() or ["C:"]
    except Exception:
        drives = ["C:"]
    pick = app.seg(r, drives)
    pick.set(drives[0])
    pick.pack(side="left")
    out = app.label(body, "", 13, wrap=820)
    def show(res):
        lo, hi = res["typical"]
        msg = t("Sequential read {r} MB/s, write {w} MB/s, random 4K read {iops} IOPS ({mb} MB/s).", r=res["seq_read"],
                w=res["seq_write"], iops=res["rand_iops"], mb=res["rand_mb"])
        if lo:
            msg += "\n" + t("A healthy {kind} usually reads {lo}-{hi} MB/s.", kind=t(res["kind"]), lo=lo, hi=hi) + " "
            msg += t("This drive is slower than usual: check free space, the cable/slot and the drive's health.") \
                if res["verdict"] == "Slow" else t("This drive is in the normal range.")
        out.configure(text=msg, text_color=WARN if res["verdict"] == "Slow" else ACCENT)
    def run():
        out.configure(text=t("Testing {d} (about 20 seconds)...", d=pick.get()), text_color=MUTED)
        app.bg(lambda: disk.bench(pick.get()), show, lambda m: out.configure(text=m, text_color=WARN))
    app.button(r, t("Speed test"), run).pack(side="left", padx=8)
    out.pack(anchor="w", pady=(6, 0))

def _scan(app, body, ds):
    """Surface scan: reads every sector of one disk (read-only) and counts unreadable and slow blocks."""
    if not ds or getattr(body, "_scan", None):
        return
    body._scan = True
    names = {f"{d['name']} ({d['size_gb']} GB)": d for d in ds}
    r = app.row(body, (10, 0))
    pick = ctk.CTkOptionMenu(r, values=list(names), width=300, height=32, fg_color=CARD2, button_color=CARD2,
                             button_hover_color=HOVER2, text_color=TEXT)
    pick.pack(side="left")
    out = app.label(body, "", 13, wrap=880)
    state = {}
    def tick():
        if not out.winfo_exists() or not state.get("total"):
            return
        pct = state["done"] * 100 / state["total"]
        out.configure(text=t("Scanning: {p:.1f}%  ·  unreadable blocks {b}  ·  slow blocks {s}", p=pct,
                             b=len(state["bad"]), s=state["slow"]), text_color=MUTED)
        if state.get("running"):
            app.after(500, tick)
    def done(st):
        st["running"] = False
        btn.configure(text=t("Surface scan"))
        bad, slow = len(st["bad"]), st["slow"]
        if st.get("stop") and st["done"] < st["total"]:
            msg, col = t("Stopped at {p:.1f}%.", p=st["done"] * 100 / max(1, st["total"])), MUTED
        elif bad:
            msg, col = t("{n} MB could not be read (bad sectors). Back up your files and replace the drive.", n=bad), WARN
        elif slow > 10:
            msg, col = t("No unreadable sectors, but {n} blocks were very slow: the drive is retrying. Back up and "
                         "check again later.", n=slow), WARN
        else:
            msg, col = t("Every sector was read without errors."), ACCENT
        out.configure(text=msg, text_color=col)
    def fail(m):
        state["running"] = False
        btn.configure(text=t("Surface scan"))
        out.configure(text=m, text_color=WARN)
    def run():
        if state.get("running"):
            state["stop"] = True
            return
        d = names[pick.get()]
        if not app.ask(t("Surface scan"), t("Read all of {name}? Nothing is written. It takes about {m} minutes on an "
                       "HDD and less on an SSD; you can keep using the PC and stop at any time.", name=d["name"],
                       m=max(1, round(d["bytes"] / 150e6 / 60)))):
            return
        state.clear()
        state["running"] = True
        btn.configure(text=t("Stop"))
        app.bg(lambda: disk.surface_scan(d["number"], d["bytes"], state), done, fail)
        app.after(800, tick)
    btn = app.button(r, t("Surface scan"), run, primary=False)
    btn.pack(side="left", padx=8)
    out.pack(anchor="w", pady=(6, 0))

def _partitions(app, p):
    """Partition layout per disk; resize NTFS partitions and make a new drive from free space (Windows Storage API)."""
    from core import partition
    body = app.card(p, t("Partitions"), t("Change the size of a drive or make a new drive from free space. Windows "
                    "says how far each drive can shrink or grow; files that cannot be moved limit shrinking. Back up "
                    "important files first."))
    bars = ctk.CTkFrame(body, fg_color="transparent")
    bars.pack(fill="x")
    tree = app.table(body, [("drive", t("Drive")), ("label", t("Name")), ("fs", t("File system")),
                            ("size", t("Size (GB)")), ("free", t("Free (GB)")), ("disk", t("Disk"))],
                     (80, 200, 100, 100, 100, 260), 6)
    msg = app.label(body, "", 12, muted=True, wrap=880)
    data = {}
    colors = {"sys": "#55606e", "data": ACCENT, "free": CARD2}
    def draw(lay):
        data.clear()
        data.update(lay)
        for w in bars.winfo_children():
            w.destroy()
        tree.delete(*tree.get_children())
        for d in lay["disks"]:
            app.label(bars, f"{t('Disk')} {d['n']}: {d['name']} ({round(d['size'] / 1e9)} GB, {d['style']})", 12,
                      muted=True).pack(anchor="w", pady=(6, 2))
            cv = ctk.CTkCanvas(bars, height=26, bg=CARD, highlightthickness=0)
            cv.pack(fill="x")
            parts = [x for x in lay["parts"] if x["disk"] == d["n"]]
            def paint(e, cv=cv, d=d, parts=parts):
                cv.delete("all")
                W, x0 = e.width, 0
                free = d["free"] if d["free"] and d["free"] > 1e9 else 0
                ws = [max(28, W * x["size"] / d["size"]) for x in parts] + ([max(90, W * free / d["size"])] if free else [])
                k = min(1, W / sum(ws)) if ws else 1  # small partitions get a minimum width; the rest shrinks to fit
                for x, w in zip(parts, ws):
                    w *= k
                    kind = "sys" if partition.changeable(x) and not x.get("letter") else "data"
                    cv.create_rectangle(x0, 2, x0 + w - 2, 24, fill=colors[kind], width=0)
                    cv.create_text(x0 + 6, 13, anchor="w", fill=ON_ACCENT if kind == "data" else TEXT,
                                   text=(x.get("letter") or "") + (f" {round(x['size'] / 1e9)}G" if w > 70 else ""))
                    x0 += w
                if free:
                    cv.create_rectangle(x0, 2, W, 24, fill=colors["free"], width=0)
                    cv.create_text(x0 + 6, 13, anchor="w", fill=TEXT, text=t("Free {g} GB", g=round(d["free"] / 1e9)))
            cv.bind("<Configure>", paint)
            for x in parts:
                if x.get("letter"):
                    tree.insert("", "end", iid=f"{x['disk']}:{x['num']}", values=(
                        x["letter"] + ":", x.get("label") or "", x.get("fs") or "", round(x["size"] / 1e9, 1),
                        round((x.get("free") or 0) / 1e9, 1), f"{d['n']}: {d['name']}"))
    def load():
        msg.configure(text=t("Reading the disks..."), text_color=MUTED)
        app.bg(partition.layout, lambda lay: (draw(lay), msg.configure(text="")),
               lambda m: msg.configure(text=m, text_color=WARN))
    def picked():
        sel = tree.selection()
        if not sel:
            msg.configure(text=t("Select a drive in the list first."), text_color=WARN)
            return None
        disk, num = map(int, sel[0].split(":"))
        return next(x for x in data["parts"] if x["disk"] == disk and x["num"] == num)
    def on_battery():
        import psutil
        b = psutil.sensors_battery()
        if b and not b.power_plugged:
            msg.configure(text=t("Connect the charger first: a power loss while resizing can damage the drive."),
                          text_color=WARN)
            return True
        return False
    def change():
        x = picked()
        if not x or on_battery():
            return
        why = partition.changeable(x)
        if why:
            return msg.configure(text=t(why), text_color=WARN)
        msg.configure(text=t("Asking Windows how far {d}: can change...", d=x["letter"]), text_color=MUTED)
        def got(res):
            (lo, hi), locked = res
            msg.configure(text="")
            ask_size(x, lo, hi, locked)
        app.bg(lambda: (partition.supported(x["disk"], x["num"]), partition.bitlocker_on(x["letter"])), got,
               lambda m: msg.configure(text=m, text_color=WARN))
    def ask_size(x, lo, hi, locked):
        cur, gb = x["size"], lambda b: round(b / 2**30, 1)
        if hi - lo < 2**30:
            return msg.configure(text=t("{d}: cannot change size now (possible {a}-{b} GB). To grow, the free space "
                                        "must be right after it on the disk; a recovery partition often sits there.",
                                        d=x["letter"], a=gb(lo), b=gb(hi)), text_color=WARN)
        d = ctk.CTkInputDialog(title=t("Change size"), text=t("{d}: is {c} GB now. New size in GB ({a} to {b}):",
                               d=x["letter"], c=gb(cur), a=gb(lo), b=gb(hi)))
        try:
            new = int(float(d.get_input() or "") * 2**30)
        except ValueError:
            return
        new = max(lo, min(hi, new))
        warn = t("BitLocker is on for this drive. ") if locked else ""
        what = t("shrink") if new < cur else t("grow")
        if not app.ask(t("Change size"), warn + t("{what} {d}: from {a} GB to {b} GB? Back up important files "
                       "first.", what=what, d=x["letter"], a=gb(cur), b=gb(new)), warn=True):
            return
        if not app.ask(t("Check once more"), t("Do not turn off the PC until it finishes. Continue?"), warn=True):
            return
        msg.configure(text=t("Changing the size... this can take several minutes."), text_color=MUTED)
        app.bg(lambda: partition.resize(x["disk"], x["num"], new),
               lambda _: (msg.configure(text=t("Done."), text_color=ACCENT), load()),
               lambda m: msg.configure(text=m, text_color=WARN))
    def new_drive():
        free = [d for d in data.get("disks", []) if (d["free"] or 0) > 1e9]
        if not free:
            return msg.configure(text=t("No free space on any disk. Shrink a drive first."), text_color=WARN)
        d = free[0] if len(free) == 1 else next((d for d in free if tree.selection() and
                                                 tree.selection()[0].startswith(f"{d['n']}:")), free[0])
        if on_battery() or not app.ask(t("New drive"), t("Make a new NTFS drive from the {g} GB of free space on "
                                       "disk {n}?", g=round(d["free"] / 1e9), n=d["n"])):
            return
        msg.configure(text=t("Making the drive..."), text_color=MUTED)
        app.bg(lambda: partition.new_drive(d["n"]),
               lambda letter: (msg.configure(text=t("New drive {d}: is ready.", d=letter), text_color=ACCENT), load()),
               lambda m: msg.configure(text=m, text_color=WARN))
    r = app.row(body, (8, 0))
    app.button(r, t("Change size..."), change).pack(side="left")
    app.button(r, t("New drive from free space"), new_drive, primary=False).pack(side="left", padx=6)
    app.button(r, t("Refresh"), load, primary=False).pack(side="left")
    msg.pack(anchor="w", pady=(6, 0))
    load()

def _temps(app, p):
    body = app.card(p, t("Temperatures"), t("CPU temperature needs the PawnIO driver (Cooling > Temperatures and fans). "
                    "Without it the app shows the firmware's thermal zone, which is often not the CPU itself."))
    lbl = app.label(body, t("Checking..."), 13, wrap=820)
    lbl.pack(anchor="w")
    try:
        usage = gpuinfo.Usage()
    except Exception:
        usage = None
    state = {"acpi": None}
    def tick():
        lines, hw = [], getattr(app, "hw", None)
        cpu = hw.cpu_temp() if hw else None
        if cpu is not None:
            lines.append(t("CPU: {v}°C", v=cpu))
        else:
            if state["acpi"] is None:
                try:
                    state["acpi"] = sensors.acpi_temps()
                except Exception:
                    state["acpi"] = []
            lines += [t("Thermal zone {n}: {v}°C", n=z["name"], v=z["value"]) for z in state["acpi"]]
            if not state["acpi"]:
                lines.append(t("CPU: not available without PawnIO"))
        for g in app.cached(("gpu", id(usage)), lambda: gpuinfo.snapshot(usage), []):
            if g["temp"]:
                lines.append(f"{g['name']}: {g['temp']:.0f}°C")
        hot = cpu is not None and cpu >= 90
        lbl.configure(text="\n".join(lines), text_color=WARN if hot else TEXT)
    app.every(3000, tick, lbl, "Diagnostics")
