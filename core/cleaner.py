"""Rule-based cleanup candidates. Nothing leaves the PC; selected items go to the Recycle Bin."""
import glob, os, re, time
from pathlib import Path
from send2trash import send2trash
from .i18n import t

INSTALLER_EXT = {".exe", ".msi", ".zip", ".7z", ".rar", ".iso"}
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin",
             "system volume information", "recovery", "steamapps", "windowsapps"}

VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".flv", ".m4v"}
PHOTO = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".bmp", ".webp", ".raw", ".cr2", ".nef", ".arw", ".dng"}
MUSIC = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma"}
# kind: (folders under the user folder, extensions or None = any, min MB, min age in days)
FOLDER_KINDS = {"video": (("Videos", "Downloads", "Desktop"), VIDEO, 50, 0),
                "photo": (("Pictures", "Downloads", "Desktop"), PHOTO, 3, 0),
                "music": (("Music", "Downloads"), MUSIC, 5, 0),
                "download": (("Downloads",), None, 1, 30),
                "personal": (("Documents", "Desktop", "OneDrive"), None, 10, 90)}
KINDS = ["temp", "installer", "download", "video", "photo", "music", "personal", "large", "leftover", "save"]
DEFAULT_KINDS = ["temp", "installer", "download", "large", "leftover"]
LEFTOVER_ROOTS = ("LOCALAPPDATA", "APPDATA", "ProgramData")
LEFTOVER_SKIP = {"microsoft", "windows", "packages", "programs", "temp", "crashdumps", "comms", "d3dscache",
                 "connecteddevicesplatform", "assembly", "nvidia corporation"}
WHOLE_FOLDER = ("leftover", "save")   # these rows are folders: they go to the Recycle Bin as a whole
# words too common to tell apps apart (a folder is not protected just because it contains them)
STOP = {"microsoft", "windows", "update", "updater", "setup", "tools", "service", "services", "system", "driver",
        "drivers", "common", "files", "data", "corporation", "software", "program", "programs", "launcher", "client",
        "helper", "runtime", "edition", "studio", "desktop", "games", "game", "local", "cache", "temp", "user",
        "users", "settings", "support", "shared", "application", "applications", "online", "office", "player"}

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

def scan(drive=None, kinds=DEFAULT_KINDS, min_mb=200, old_days=180, installer_days=30):
    """drive: 'D:' to look only for large old files on that drive; None = system drive. kinds: which of KINDS to
    look for. Anything whose name matches an app on this PC is left out."""
    home, kinds = Path.home(), set(kinds)
    cands = []
    keep = protected()
    if drive and drive.upper() != home.drive.upper():
        if "large" in kinds:
            _large(drive + "\\", cands, min_mb, old_days, keep)
        return cands
    for tmp in ({os.environ.get("TEMP"), r"C:\Windows\Temp"} - {None}) if "temp" in kinds else ():
        cands.append({"path": tmp, "size_mb": round(_dir_size(tmp) / 2**20), "age_days": 0, "kind": "temp",
                      "reason": t("Temp folder (only its contents are removed)")})
    dl = home / "Downloads"
    if dl.is_dir() and "installer" in kinds:
        for f in dl.iterdir():
            if f.is_file() and f.suffix.lower() in INSTALLER_EXT:
                st = f.stat()
                if _age_days(st) >= installer_days:
                    cands.append({"path": str(f), "size_mb": round(st.st_size / 2**20), "kind": "installer",
                                  "age_days": _age_days(st), "reason": t("Old installer or archive in Downloads")})
    for k in ("video", "photo", "music", "download", "personal"):
        if k in kinds:
            _folders(k, cands, keep)
    if "leftover" in kinds:
        _leftover(cands, keep)
    if "save" in kinds:
        _saves(cands)
    if "large" in kinds:
        _large(home, cands, min_mb, old_days, keep)
    seen, out = set(), []
    for c in cands:  # one row per path (a video in Downloads is listed once, as a video)
        if c["path"].lower() not in seen:
            seen.add(c["path"].lower())
            out.append(c)
    return out

REASONS = {"video": "Video", "photo": "Photo", "music": "Music", "download": "In Downloads, not opened for a month",
           "personal": "Your file, not changed for 3 months - check first"}

def _folders(kind, cands, keep, limit=1500):
    dirs, exts, min_mb, min_age = FOLDER_KINDS[kind]
    n = 0
    for name in dirs:
        base = Path.home() / name
        for root, sub, files in (os.walk(base) if base.is_dir() else []):
            sub[:] = [d for d in sub if not d.startswith(".") and not _is_protected(d, keep)]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if (exts and ext not in exts) or (kind == "download" and ext in INSTALLER_EXT | VIDEO | PHOTO | MUSIC):
                    continue
                p = os.path.join(root, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if st.st_size >= min_mb * 2**20 and _age_days(st) >= min_age:
                    cands.append({"path": p, "size_mb": round(st.st_size / 2**20), "kind": kind,
                                  "age_days": _age_days(st), "reason": t(REASONS[kind])})
                    n += 1
                    if n >= limit:
                        return

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())

def protected():
    """Names of apps on this PC: (whole names, single words). From the uninstall list, the app index (Steam, Store,
    ...), Store packages, Program Files, Start menu shortcuts and running programs."""
    import psutil
    from . import appsdb
    names = []
    try:
        for v in appsdb._uninstall_entries():
            names.append(v["DisplayName"])
            names.append(os.path.basename((v.get("InstallLocation") or "").rstrip("\\")))
    except Exception:
        pass
    for a in appsdb.load_cache() or []:
        names += [a.get("name") or "", os.path.splitext(os.path.basename(a.get("exe") or ""))[0],
                  os.path.basename((a.get("folder") or "").rstrip("\\"))]
    pkgs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    dirs = [pkgs, os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", ""),
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
            os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs")]
    for d in dirs:
        try:
            for n in os.listdir(d):
                names.append(n.split("_")[0] if d == pkgs else os.path.splitext(n)[0])
        except OSError:
            pass
    running = set()
    for p in psutil.process_iter(["exe"]):
        exe = p.info.get("exe") or ""
        if exe:
            names.append(os.path.splitext(os.path.basename(exe))[0])
            running.add(os.path.dirname(exe).lower())
    whole = {_norm(n) for n in names if len(_norm(n)) >= 4}
    words = {w for n in names for w in re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", n).lower())
             if len(w) >= 4 and w not in STOP}
    return whole, words, running

def _is_protected(name, keep, path=None):
    whole, words, running = keep
    n = _norm(name)
    if len(n) < 4:
        return False
    if n in whole or any(w in n for w in words) or any(n in x for x in whole):
        return True
    return bool(path) and any(r.startswith(path.lower()) for r in running)

def _leftover(cands, keep, min_mb=10):
    """Folders in AppData and ProgramData that match no app on this PC: a guess, so they are not ticked."""
    for var in LEFTOVER_ROOTS:
        root = os.environ.get(var) or os.path.expandvars("%" + var + "%")
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for n in entries:
            p = os.path.join(root, n)
            if n.lower() in LEFTOVER_SKIP or not os.path.isdir(p) or _is_protected(n, keep, p) or len(_norm(n)) < 4:
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

def _large(top, cands, min_mb, old_days, keep):
    for root, dirs, files in os.walk(top):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".") and not _is_protected(d, keep)]
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
