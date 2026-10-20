"""Installed apps for the app list: name, exe, icon source, uninstall command, game or not.
Sources: Uninstall registry keys, Start menu shortcuts, Steam and Epic libraries."""
import glob, json, os, re, time
from . import games
from .finder import SKIP, _main_exe, _shortcuts
from .reg import HKCU, HKLM

UNINSTALL = [(HKLM, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
             (HKLM, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
             (HKCU, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")]
EPIC = r"%ProgramData%\Epic\EpicGamesLauncher\Data\Manifests"

def _uninstall_entries():
    import winreg
    out = []
    for root, path in UNINSTALL:
        try:
            k = winreg.OpenKey(root, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(k)[0]):
            try:
                sub = winreg.OpenKey(k, winreg.EnumKey(k, i))
                v = {}
                for name in ("DisplayName", "DisplayIcon", "InstallLocation", "UninstallString",
                             "QuietUninstallString", "SystemComponent", "ParentKeyName", "EstimatedSize"):
                    try:
                        v[name] = winreg.QueryValueEx(sub, name)[0]
                    except OSError:
                        pass
            except OSError:
                continue
            if v.get("DisplayName") and v.get("UninstallString") and not v.get("SystemComponent") \
                    and not v.get("ParentKeyName"):
                out.append(v)
    return out

def _icon_path(s):
    """'C:\\x\\app.exe,0' -> ('C:\\x\\app.exe', 0)"""
    if not s:
        return None, 0
    m = re.match(r'^"?(.*?)"?(?:,(-?\d+))?$', s.strip())
    return (m.group(1), int(m.group(2) or 0)) if m else (None, 0)

def scan():
    apps = {}
    def add(name, exe=None, icon=None, uninstall=None, location=None, game=False, source=None, size_mb=None):
        key = (exe or name).lower()
        a = apps.setdefault(key, {"name": name, "exe": exe, "icon": icon or exe, "uninstall": None,
                                  "location": location, "game": False, "source": source, "size_mb": size_mb})
        a["uninstall"] = a["uninstall"] or uninstall
        a["location"] = a["location"] or location
        a["source"] = a["source"] or source
        a["size_mb"] = a["size_mb"] or size_mb
        a["game"] = a["game"] or game
        if not a["icon"] and icon:
            a["icon"] = icon
    for name, exe in _shortcuts():
        if not any(s in name.lower() for s in SKIP):
            add(name, exe)
    try:
        for g in games.steam_games():
            add(g["name"], _main_exe(g["path"]), location=g["path"], game=True, source="Steam")
    except Exception:
        pass
    for f in glob.glob(os.path.join(os.path.expandvars(EPIC), "*.item")):
        try:
            d = json.load(open(f, encoding="utf-8"))
            loc = d.get("InstallLocation", "")
            exe = os.path.join(loc, d.get("LaunchExecutable", ""))
            add(d.get("DisplayName", os.path.basename(loc)), exe if os.path.isfile(exe) else None, location=loc, game=True,
                source="Epic")
        except Exception:
            pass
    # attach uninstall commands and icons from the registry, matching by install folder or name
    by_dir = {}
    for a in apps.values():
        if a["exe"]:
            by_dir.setdefault(os.path.dirname(a["exe"]).lower(), a)
    for v in _uninstall_entries():
        icon, _ = _icon_path(v.get("DisplayIcon"))
        icon = icon if icon and os.path.isfile(icon) and icon.lower().endswith((".exe", ".ico", ".dll")) else None
        loc = (v.get("InstallLocation") or "").rstrip("\\").lower()
        match = next((a for d, a in by_dir.items() if loc and (d == loc or d.startswith(loc + "\\"))), None)
        match = match or next((a for a in apps.values() if a["name"].lower() == v["DisplayName"].lower()), None)
        cmd = v.get("UninstallString")
        size = round(int(v["EstimatedSize"]) / 1024) if str(v.get("EstimatedSize", "")).isdigit() else None  # KB
        if match:
            match["uninstall"] = match["uninstall"] or cmd
            match["icon"] = match["icon"] or icon
            match["location"] = match["location"] or v.get("InstallLocation") or None
            match["size_mb"] = match["size_mb"] or size
        else:
            add(v["DisplayName"], None, icon, cmd, v.get("InstallLocation") or None, size_mb=size)
    out = sorted(apps.values(), key=lambda a: a["name"].lower())
    for a in out:
        a["folder"] = folder(a)
        a["drive"] = (a["folder"] or "")[:2].upper()
        a["source"] = a["source"] or classify(a["folder"])
    save_cache(out)
    return out

CACHE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "PCOptimizer", "apps.json")
SYSTEM_ROOTS = {os.path.normcase(os.path.expandvars(p)) for p in (r"%SystemRoot%", r"%ProgramFiles%",
                r"%ProgramFiles(x86)%", r"%ProgramData%", r"%LOCALAPPDATA%", r"%APPDATA%", r"%USERPROFILE%",
                r"%LOCALAPPDATA%\Programs")}

def folder(a):
    """The app's own install folder (never a shared root like Program Files)."""
    f = (a.get("location") or (os.path.dirname(a["exe"]) if a.get("exe") else "") or "").strip('"').rstrip("\\")
    return f if f and os.path.normcase(f) not in SYSTEM_ROOTS and len(f) > 3 else ""

def classify(f):
    lf = (f or "").lower()
    if not lf:
        return "Other"
    if "steamapps" in lf:
        return "Steam"
    if "\\windowsapps\\" in lf:
        return "Microsoft Store"
    if "\\program files" in lf:
        return "Program Files"
    if lf.startswith(os.path.expanduser("~").lower()):
        return "User folder"
    return "Other"

def save_cache(apps):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(apps, f)
    except OSError:
        pass

def load_cache():
    """Last scan, shown instantly at start-up while a fresh scan runs."""
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []

def folder_size_mb(path, limit_s=20):
    total, t0, stack = 0, time.time(), [path]
    while stack:
        if time.time() - t0 > limit_s:
            break
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return round(total / 2**20)

def run(a):
    os.startfile(a["exe"])

def uninstall(a):
    """Runs the app's own uninstaller (it shows its own window)."""
    import subprocess
    cmd = a["uninstall"]
    if not cmd:
        raise RuntimeError("no uninstaller")
    subprocess.Popen(cmd, shell=True)
