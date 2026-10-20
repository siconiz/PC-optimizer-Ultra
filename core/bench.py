"""Frame time capture with Intel PresentMon (MIT, bundled in the tools folder)."""
import csv, glob, os, subprocess, sys, tempfile
from collections import Counter
import psutil
from .i18n import t

def presentmon_path():
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hits = sorted(glob.glob(os.path.join(base, "tools", "PresentMon*.exe")))
    return hits[-1] if hits else None

def summarize(path):
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("MsBetweenPresents") or "").replace(".", "", 1).isdigit()]
    if rows:  # keep the busiest swap chain (ignores overlays and launchers)
        main = Counter(r.get("SwapChainAddress") for r in rows).most_common(1)[0][0]
        rows = [r for r in rows if r.get("SwapChainAddress") == main]
    ms = sorted(float(r["MsBetweenPresents"]) for r in rows if float(r["MsBetweenPresents"]) > 0)
    if len(ms) < 30:
        raise RuntimeError(t("Too few frames captured. Keep the game in the foreground and in gameplay."))
    p99 = ms[max(0, int(len(ms) * 0.99) - 1)]
    return {"frames": len(ms), "avg_fps": round(1000 * len(ms) / sum(ms), 1),
            "low1_fps": round(1000 / p99, 1), "p99_ms": round(p99, 2)}

def capture(process, seconds):
    exe = presentmon_path()
    if not exe:
        raise RuntimeError(t("PresentMon was not found in the tools folder."))
    if not any((p.info["name"] or "").lower() == process.lower() for p in psutil.process_iter(["name"])):
        raise RuntimeError(t("{p} is not running. Start the game first.", p=process))
    out = os.path.join(tempfile.gettempdir(), "pcoptimizer_frames.csv")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([exe, "--process_name", process, "--output_file", out, "--timed", str(seconds),
                    "--terminate_after_timed", "--stop_existing_session", "--no_console_stats",
                    "--session_name", "PCOptimizer"],
                   capture_output=True, timeout=seconds + 60, creationflags=0x08000000)
    if not os.path.exists(out):
        raise RuntimeError(t("PresentMon produced no data."))
    return summarize(out)
