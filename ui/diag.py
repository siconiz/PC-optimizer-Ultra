"""Diagnostics page: network, drives (health + speed), temperatures."""
import customtkinter as ctk
from core import disk, gpuinfo, net, sensors
from core.i18n import t
from .theme import ACCENT, MUTED, TEXT, WARN

def page(app, p):
    _network(app, p)
    _drives(app, p)
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
    body = app.card(p, t("Drives"), t("Health comes from Windows (SMART data). The speed test writes a temporary file "
                    "and reads it back without the Windows cache, then compares the result with what that kind of "
                    "drive usually reaches."))
    tree = app.table(body, [("name", t("Drive")), ("type", t("Type")), ("size", t("Size (GB)")), ("health", t("Health")),
                            ("temp", t("Temperature")), ("wear", t("Wear")), ("hours", t("Power-on hours"))],
                     (260, 110, 80, 90, 100, 70, 110), 4, {"bad": WARN})
    def fill(ds):
        tree.delete(*tree.get_children())
        for d in ds:
            bad = d["health"] != "Healthy" or (d["wear"] or 0) >= 80 or d["errors"]
            tree.insert("", "end", tags=("bad",) if bad else (), values=(
                d["name"], f"{d['media']} / {d['bus']}", d["size_gb"], t(d["health"]),
                f"{d['temp']}°C" if d["temp"] else "-", f"{d['wear']}%" if d["wear"] is not None else "-",
                d["hours"] or "-"))
    app.bg(disk.health, fill, lambda m: None)
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

def _temps(app, p):
    body = app.card(p, t("Temperatures"), t("CPU temperature needs the PawnIO driver (Graphics & Cooling > Temperatures and fans). "
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
