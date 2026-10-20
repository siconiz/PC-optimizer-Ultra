"""Ultimate Performance only while a listed game runs."""
import os, re, subprocess, threading
import psutil
from .i18n import t

ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"
GUID = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
NOWIN = 0x08000000  # CREATE_NO_WINDOW

def pc(*args):
    return subprocess.run(["powercfg", *args], capture_output=True, text=True,
                          creationflags=NOWIN).stdout

def active_scheme():
    return re.search(GUID, pc("/getactivescheme")).group(0)

SAVED = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "PCOptimizer", "ultimate.txt")

def find_ultimate():
    """GUID of the Ultimate Performance plan on this PC, or None. The plan's name is translated by Windows, so the
    GUID this app created is remembered instead of searching by name."""
    plans = pc("/list")
    if ULTIMATE in plans.lower():
        return ULTIMATE
    try:
        with open(SAVED) as f:
            guid = f.read().strip()
        if guid and guid.lower() in plans.lower():
            return guid
    except OSError:
        pass
    for line in plans.splitlines():  # English Windows, or a plan someone added by hand
        if "Ultimate" in line and (m := re.search(GUID, line)):
            return m.group(0)
    return None

def unlock_ultimate(activate=False):
    """Adds Microsoft's hidden Ultimate Performance plan (powercfg -duplicatescheme e9a42b02-...) once, so it shows
    up in Control Panel > Power Options. Returns its GUID, or None where Windows does not offer it (for example PCs
    with Modern Standby, which only have the Balanced plan)."""
    guid = find_ultimate()
    if not guid:
        m = re.search(GUID, pc("-duplicatescheme", ULTIMATE))
        guid = m.group(0) if m else None
        if guid:
            try:
                os.makedirs(os.path.dirname(SAVED), exist_ok=True)
                with open(SAVED, "w") as f:
                    f.write(guid)
            except OSError:
                pass
    if guid and activate:
        pc("/setactive", guid)
    return guid

def ultimate_scheme():
    return unlock_ultimate() or "SCHEME_MIN"  # High performance if Ultimate is not offered

class GameWatcher(threading.Thread):
    def __init__(self, names, log):
        super().__init__(daemon=True)
        self.names = {n.lower() for n in names}
        self.log = log
        self.stop_evt = threading.Event()

    def running(self):
        return any((p.info["name"] or "").lower() in self.names
                   for p in psutil.process_iter(["name"]))

    def run(self):
        target, saved = ultimate_scheme(), None
        self.log(t("Watching: {names}", names=", ".join(sorted(self.names))))
        try:
            while not self.stop_evt.wait(5):
                on = self.running()
                if on and saved is None:
                    saved = active_scheme()
                    pc("/setactive", target)
                    self.log(t("Game detected: performance plan on"))
                elif not on and saved:
                    pc("/setactive", saved)
                    saved = None
                    self.log(t("Game closed: plan restored"))
        finally:
            if saved:
                pc("/setactive", saved)
            self.log(t("Stopped"))

    def stop(self):
        self.stop_evt.set()
