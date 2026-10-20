"""Move an app's folder to another drive and leave a directory junction at the old path, so shortcuts, the
registry and the uninstaller keep working. Steam and Microsoft Store apps use their own built-in move instead."""
import os, shutil, subprocess
import psutil

NOWIN = 0x08000000

def running_from(folder):
    f = os.path.normcase(folder) + os.sep
    out = []
    for p in psutil.process_iter(["exe", "name"]):
        exe = os.path.normcase(p.info["exe"] or "")
        if exe.startswith(f):
            out.append(p.info["name"])
    return sorted(set(out))

def is_junction(path):
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (OSError, AttributeError):
        return False

def move(folder, dest_root, progress=None):
    """Copy -> verify -> rename original -> junction -> delete original. Any failure rolls back."""
    src = os.path.normpath(folder)
    if is_junction(src):
        raise RuntimeError("already moved")
    if busy := running_from(src):
        raise RuntimeError(", ".join(busy))
    dest = os.path.join(dest_root, "PCOptimizer Apps", os.path.basename(src))
    if os.path.exists(dest):
        raise FileExistsError(dest)
    need = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(src) for f in fs)
    if shutil.disk_usage(dest_root).free < need * 1.05:
        raise OSError("not enough space")
    if progress:
        progress("copy")
    shutil.copytree(src, dest, symlinks=True)
    copied = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dest) for f in fs)
    old = src + ".pcopt-old"
    try:
        if copied != need:
            raise OSError("copy incomplete")
        os.rename(src, old)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", src, dest], capture_output=True, text=True,
                           creationflags=NOWIN)
        if r.returncode:
            raise OSError(r.stdout + r.stderr)
    except Exception:
        if os.path.exists(old) and not os.path.exists(src):
            os.rename(old, src)
        shutil.rmtree(dest, ignore_errors=True)
        raise
    if progress:
        progress("cleanup")
    shutil.rmtree(old, ignore_errors=True)
    return dest

def open_steam_storage():
    os.startfile("steam://open/settings")  # Steam > Settings > Storage moves games between libraries

def open_store_move():
    os.startfile("ms-settings:appsfeatures")  # Installed apps > ... > Move
