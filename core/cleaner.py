"""Rule-based cleanup candidates. Nothing leaves the PC; selected items go to the Recycle Bin."""
import os, time
from pathlib import Path
from send2trash import send2trash
from .i18n import t

INSTALLER_EXT = {".exe", ".msi", ".zip", ".7z", ".rar", ".iso"}
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin",
             "system volume information", "recovery", "steamapps", "windowsapps"}

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
    _large(home, cands, min_mb, old_days)
    return cands

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

def trash(paths):
    """Temp folders are emptied (children only); files in use are skipped."""
    done = 0
    for p in paths:
        try:
            targets = [os.path.join(p, c) for c in os.listdir(p)] if os.path.isdir(p) else [p]
        except OSError:
            continue
        for item in targets:
            try:
                send2trash(item)
                done += 1
            except Exception:
                pass
    return done
