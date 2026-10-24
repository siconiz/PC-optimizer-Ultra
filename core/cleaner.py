"""Rule-based cleanup candidates. Nothing leaves the PC; selected items go to the Recycle Bin."""
import glob, os, time
from pathlib import Path
from send2trash import send2trash
from .i18n import t

INSTALLER_EXT = {".exe", ".msi", ".zip", ".7z", ".rar", ".iso"}
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin",
             "system volume information", "recovery", "steamapps", "windowsapps"}

MEDIA = {".mp4": 50, ".mkv": 50, ".mov": 50, ".avi": 50, ".wmv": 50,            # videos: min size in MB
         ".jpg": 5, ".jpeg": 5, ".png": 5, ".heic": 5, ".gif": 5, ".bmp": 5, ".raw": 5, ".cr2": 5, ".nef": 5,
         ".mp3": 10, ".flac": 10, ".wav": 10, ".m4a": 10, ".ogg": 10}
MEDIA_DIRS = ("Videos", "Pictures", "Music", "Downloads")
LEFTOVER_ROOTS = ("LOCALAPPDATA", "APPDATA", "ProgramData")
LEFTOVER_SKIP = {"microsoft", "windows", "packages", "programs", "temp", "crashdumps", "comms", "d3dscache",
                 "connecteddevicesplatform", "assembly", "nvidia corporation"}
WHOLE_FOLDER = ("leftover", "save")   # these rows are folders: they go to the Recycle Bin as a whole

def _age_days(st):
    return int((time.time() - st.st_mtime) / 86400)

def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for n in files:
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    return total

def scan(drive=None, min_mb=200, old_days=180, installer_days=30):
    """drive: 'D:' to look only for large old files on that drive; None = system drive (temp, Downloads, home)."""
    home = Path.home()
    cands = []
    if drive and drive.upper() != home.drive.upper():
        _large(drive + "\\", cands, min_mb, old_days)
        return cands
    for tmp in {os.environ.get("TEMP"), r"C:\Windows\Temp"} - {None}:
        cands.append({"path": tmp, "size_mb": round(_dir_size(tmp) / 2**20), "age_days": 0, "kind": "temp",
                      "reason": t("Temp folder (only its contents are removed)")})
    dl = home / "Downloads"
    if dl.is_dir():
        for f in dl.iterdir():
            if f.is_file() and f.suffix.lower() in INSTALLER_EXT:
                st = f.stat()
                if _age_days(st) >= installer_days:
                    cands.append({"path": str(f), "size_mb": round(st.st_size / 2**20), "kind": "installer",
                                  "age_days": _age_days(st), "reason": t("Old installer or archive in Downloads")})
    _media(cands)
    _leftover(cands)
    _saves(cands)
    _large(home, cands, min_mb, old_days)
    return cands

def _media(cands, limit=2000):
    """Photos, videos and music over a minimum size in the usual folders. Never ticked by 'Select temp files'."""
    for name in MEDIA_DIRS:
        base = Path.home() / name
        for root, _, files in (os.walk(base) if base.is_dir() else []):
            for f in files:
                p = os.path.join(root, f)
                ext = os.path.splitext(f)[1].lower()
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if ext in MEDIA and st.st_size >= MEDIA[ext] * 2**20:
                    cands.append({"path": p, "size_mb": round(st.st_size / 2**20), "kind": "media",
                                  "age_days": _age_days(st),
                                  "reason": t("Photo, video or music file - check before moving")})
                    if len(cands) >= limit:
                        return

def _installed_names():
    """Lower-case names of installed apps from the uninstall list (names and install folder names)."""
    from .appsdb import _uninstall_entries
    names = set()
    for v in _uninstall_entries():
        names.add(v["DisplayName"].lower())
        if v.get("InstallLocation"):
            names.add(os.path.basename(v["InstallLocation"].rstrip("\\")).lower())
    return {n for n in names if len(n) >= 4}

def _leftover(cands, min_mb=10):
    """Folders in AppData and ProgramData whose name matches no installed app: a guess, so they are not ticked."""
    names = _installed_names()
    for var in LEFTOVER_ROOTS:
        root = os.environ.get(var) or os.path.expandvars("%" + var + "%")
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for n in entries:
            low = n.lower()
            p = os.path.join(root, n)
            if low in LEFTOVER_SKIP or len(low) < 4 or not os.path.isdir(p) or any(x in low or low in x for x in names):
                continue
            size = _dir_size(p)
            if size >= min_mb * 2**20:
                cands.append({"path": p, "size_mb": round(size / 2**20), "kind": "leftover",
                              "age_days": _age_days(os.stat(p)),
                              "reason": t("Folder of an app that is no longer installed (guess) - check first")})

def _saves(cands):
    """Steam's local copy of each game's saves and the Windows 'Saved Games' folders. Never ticked automatically."""
    from . import games
    root = games.steam_root()
    folders = glob.glob(os.path.join(root, "userdata", "*", "*", "remote")) if root else []
    folders += [str(p) for p in (Path.home() / "Saved Games").glob("*") if p.is_dir()]
    for p in folders:
        size = _dir_size(p)
        if size:
            cands.append({"path": p, "size_mb": round(size / 2**20), "kind": "save",
                          "age_days": _age_days(os.stat(p)),
                          "reason": t("Game save: may hold your progress - check before moving")})

def _large(top, cands, min_mb, old_days):
    for root, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            p = os.path.join(root, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            if st.st_size >= min_mb * 2**20 and _age_days(st) >= old_days:
                cands.append({"path": p, "size_mb": round(st.st_size / 2**20), "kind": "large",
                              "age_days": _age_days(st), "reason": t("Large file, untouched for months - check first")})

def trash(paths, whole=()):
    """Temp folders are emptied (children only); folders in `whole` go to the Recycle Bin as a whole; files in use
    are skipped."""
    done = 0
    for p in paths:
        try:
            if p in whole or not os.path.isdir(p):
                targets = [p]
            else:
                targets = [os.path.join(p, c) for c in os.listdir(p)]
        except OSError:
            continue
        for item in targets:
            try:
                send2trash(item)
                done += 1
            except Exception:
                pass
    return done
