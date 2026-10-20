"""Game boot: restart once with memory integrity (HVCI) off, then remind the user to turn it back on.
HVCI is read only at boot, so it cannot be switched for a single game without a restart."""
import subprocess, sys
from . import tweaks
from .reg import HKLM, get, set_value

TASK = "PCOptimizer game boot"
CI_STATE = (HKLM, r"SYSTEM\CurrentControlSet\Control\CI\State", "HVCIEnabled")
NOWIN = 0x08000000

def running():
    """True when HVCI is enforced right now (Windows sets this at boot)."""
    return get(*CI_STATE) == 1

def _app_cmd():
    return f'"{sys.executable}"' if getattr(sys, "frozen", False) else f'"{sys.executable}" "{sys.argv[0]}"'

def start(cfg):
    """Turn HVCI off, open the app again after sign-in (scheduled task, runs elevated) and restart."""
    tweaks.hvci_disable()
    cfg["game_boot"] = True
    subprocess.run(["schtasks", "/Create", "/F", "/TN", TASK, "/SC", "ONLOGON", "/RL", "HIGHEST",
                    "/TR", _app_cmd() + " --after-game-boot"], capture_output=True, creationflags=NOWIN)
    subprocess.run(["shutdown", "/r", "/t", "10", "/c", "PC Optimizer: game boot"], creationflags=NOWIN)

def after_boot():
    """Called on the first start after the restart: remove the one-time task."""
    subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True, creationflags=NOWIN)

def finish(cfg, restart=False):
    """Turn memory integrity back on (takes effect after the next restart)."""
    set_value(*tweaks.HVCI, 1)
    cfg["game_boot"] = False
    if restart:
        subprocess.run(["shutdown", "/r", "/t", "10", "/c", "PC Optimizer: memory integrity back on"],
                       creationflags=NOWIN)
