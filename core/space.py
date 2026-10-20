"""Disk space: Recycle Bin, hibernation file, Windows component store, Windows.old."""
import ctypes, os, subprocess
from .cleaner import _dir_size

DRIVE = os.environ.get("SystemDrive", "C:") + "\\"

class _RB8(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]

class _RB1(ctypes.Structure):
    _pack_ = 1
    _fields_ = _RB8._fields_

def recycle_bin():
    """(MB, items) for all drives."""
    for cls in (_RB8, _RB1):  # header packing differs between SDKs; try both
        info = cls()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return round(info.i64Size / 2**20), info.i64NumItems
    return 0, 0

def empty_recycle_bin():
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7)  # no confirmation, progress or sound

def hiberfil_gb():
    try:
        return round(os.stat(os.path.join(DRIVE, "hiberfil.sys")).st_size / 2**30, 1)
    except OSError:
        return 0

def set_hibernate(on):
    subprocess.run(["powercfg", "/h", "on" if on else "off"], capture_output=True, creationflags=0x08000000)

def component_cleanup():
    r = subprocess.run(["dism.exe", "/online", "/Cleanup-Image", "/StartComponentCleanup"],
                       capture_output=True, text=True, errors="replace", creationflags=0x08000000)
    return (r.stdout or r.stderr).strip()[-1500:]

def windows_old_gb():
    p = os.path.join(DRIVE, "Windows.old")
    return round(_dir_size(p) / 2**30, 1) if os.path.isdir(p) else 0

def open_storage_settings():
    os.startfile("ms-settings:storagesense")
