"""Game install locations: Steam games (auto-detected) plus folders the user adds."""
import glob, os
from pathlib import Path
import psutil
from . import storage, vdf
from .reg import HKCU, HKLM, get

SKIP_APPIDS = {"228980"}  # Steamworks Common Redistributables

def steam_root():
    for root, path, name in ((HKLM, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                             (HKCU, r"Software\Valve\Steam", "SteamPath")):
        p = get(root, path, name)
        if p and os.path.isdir(p):
            return os.path.normpath(p)
    return None

def _read(path):
    try:
        return vdf.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return {}

def steam_libraries(root):
    libs = {os.path.normcase(root): root}
    for v in (_read(os.path.join(root, "steamapps", "libraryfolders.vdf")).get("libraryfolders") or {}).values():
        p = v.get("path") if isinstance(v, dict) else v  # new format: {"path": ...}, old format: "1" "D:\\Lib"
        if isinstance(p, str) and os.path.isdir(p):
            p = os.path.normpath(p)
            libs.setdefault(os.path.normcase(p), p)
    return list(libs.values())

def steam_games():
    root = steam_root()
    if not root:
        return []
    games = []
    for lib in steam_libraries(root):
        for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            st = _read(acf).get("appstate") or {}
            inst = st.get("installdir")
            if not inst or st.get("appid") in SKIP_APPIDS:
                continue
            path = os.path.join(lib, "steamapps", "common", inst)
            if os.path.isdir(path):
                size = st.get("sizeondisk", "")
                games.append({"name": st.get("name") or inst, "source": "Steam", "path": path,
                              "size_gb": round(int(size) / 2**30, 1) if size.isdigit() else None})
    return games

def _folder_gb(path):
    total = 0
    for r, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return round(total / 2**30, 1)

def scan(manual_paths=()):
    games = steam_games()
    known = {os.path.normcase(g["path"]) for g in games}
    for p in manual_paths:
        if os.path.isdir(p) and os.path.normcase(p) not in known:
            games.append({"name": os.path.basename(p.rstrip("\\/")) or p, "source": "Manual",
                          "path": p, "size_gb": _folder_gb(p)})
    drives = {}
    for g in games:
        d = os.path.splitdrive(g["path"])[0].upper()
        if d not in drives:
            try:
                free = round(psutil.disk_usage(d + "\\").free / 2**30)
            except Exception:
                free = None
            try:
                kind = storage.drive_kind(d)
            except Exception:
                kind = "Unknown"
            drives[d] = (kind, free)
        g["drive"], (g["kind"], g["free_gb"]) = d, drives[d]
    return sorted(games, key=lambda g: (g["kind"] != "HDD", g["name"].lower()))
