"""Find installed apps and games by name: Start menu shortcuts, Steam games and running apps."""
import glob, os
import psutil
from . import games

SKIP = ("uninst", "setup", "install", "crash", "report", "update", "helper", "redist", "vc_redist", "dxsetup", "unins")

def _shortcuts():
    roots = [os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
             os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")]
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        return []
    out = []
    for root in roots:
        for lnk in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            try:
                target = shell.CreateShortcut(lnk).TargetPath
            except Exception:
                continue
            if target.lower().endswith(".exe") and os.path.isfile(target):
                out.append((os.path.splitext(os.path.basename(lnk))[0], target))
    return out

def _main_exe(folder):
    """Largest .exe in the top two folder levels, skipping installers and crash reporters."""
    exes = glob.glob(os.path.join(folder, "*.exe")) + glob.glob(os.path.join(folder, "*", "*.exe"))
    exes = [e for e in exes if not any(s in os.path.basename(e).lower() for s in SKIP)]
    return max(exes, key=os.path.getsize) if exes else None

def index():
    items = {}
    for name, exe in _shortcuts():
        if not any(s in name.lower() for s in SKIP):
            items.setdefault(exe.lower(), (name, exe))
    try:
        for g in games.steam_games():
            exe = _main_exe(g["path"])
            if exe:
                items.setdefault(exe.lower(), (g["name"], exe))
    except Exception:
        pass
    sysroot = os.path.expandvars(r"%SystemRoot%").lower()
    for pid in psutil.pids():
        try:
            p = psutil.Process(pid)
            exe, name = p.exe(), p.name()
        except (psutil.Error, OSError):
            continue
        if exe and not exe.lower().startswith(sysroot):
            items.setdefault(exe.lower(), (os.path.splitext(name)[0], exe))
    return sorted(items.values(), key=lambda x: x[0].lower())

def search(idx, text, limit=30):
    text = text.lower().strip()
    return [x for x in idx if text in x[0].lower() or text in os.path.basename(x[1]).lower()][:limit] if text else []
