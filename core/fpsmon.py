"""Live FPS for the overlay: PresentMon writes one CSV line per frame to stdout; we keep the frames of the app in
front (foreground process) and compute FPS, average, 1% low and frame times."""
import collections, csv, io, subprocess, threading, time
from . import bench

class FpsMonitor(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.pid, self.proc, self.error = None, None, ""
        self.frames = collections.deque(maxlen=5000)   # (time, ms) of the tracked process
        self.lock, self.stop_evt, self.started = threading.Lock(), threading.Event(), time.time()

    def run(self):
        exe = bench.presentmon_path()
        if not exe:
            self.error = "PresentMon not found"
            return
        self.proc = subprocess.Popen([exe, "--output_stdout", "--no_console_stats", "--stop_existing_session",
                                      "--session_name", "PCOptimizerOverlay"], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, creationflags=0x08000000)
        reader = csv.reader(self.proc.stdout)
        try:
            header = next(reader)
        except StopIteration:
            self.error = "PresentMon gave no output"
            return
        col = {name: i for i, name in enumerate(header)}
        i_pid, i_ms = col.get("ProcessID"), col.get("MsBetweenPresents")
        if i_pid is None or i_ms is None:
            self.error = "unexpected PresentMon output"
            return
        for row in reader:
            if self.stop_evt.is_set():
                break
            try:
                if int(row[i_pid]) != self.pid:
                    continue
                ms = float(row[i_ms])
            except (ValueError, IndexError):
                continue
            if 0 < ms < 1000:
                with self.lock:
                    self.frames.append((time.time(), ms))

    def track(self, pid):
        if pid != self.pid:
            with self.lock:
                self.pid, self.started = pid, time.time()
                self.frames.clear()

    def stats(self):
        """fps (last second), avg, low1 (1% low over the last frames), ms (last frame), history of fps."""
        with self.lock:
            fr = list(self.frames)
        if len(fr) < 5:
            return None
        now = time.time()
        last = [ms for ts, ms in fr if now - ts <= 1.0]
        if not last:
            return None
        allms = [ms for _, ms in fr]
        worst = sorted(allms)[-max(1, len(allms) // 100):]
        return {"fps": round(1000 * len(last) / sum(last)), "avg": round(1000 * len(allms) / sum(allms)),
                "low1": round(1000 / (sum(worst) / len(worst))), "ms": round(fr[-1][1], 1),
                "frametimes": allms[-120:]}

    def stop(self):
        self.stop_evt.set()
        if self.proc:
            self.proc.terminate()
