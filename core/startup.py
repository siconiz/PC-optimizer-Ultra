"""Startup apps: same data Task Manager uses (Run keys, Startup folders, StartupApproved on/off state)."""
import os, re, struct, time, winreg
from send2trash import send2trash
from .reg import HKCU, HKLM, values

RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN32 = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
USER_DIR = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
COMMON_DIR = os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\StartUp")
# (scope label, registry root, Run key or folder, StartupApproved subkey)
SOURCES = [("User", HKCU, RUN, "Run"), ("All users", HKLM, RUN, "Run"), ("All users", HKLM, RUN32, "Run32"),
           ("User", HKCU, USER_DIR, "StartupFolder"), ("All users", HKLM, COMMON_DIR, "StartupFolder")]

def _target(cmd):
    m = re.match(r'\s*"([^"]+)"|\s*(\S+\.exe)', cmd or "", re.I)
    return (m.group(1) or m.group(2)) if m else ""

def _enabled(root, sub, name):
    try:
        with winreg.OpenKey(root, f"{APPROVED}\\{sub}") as k:
            data = winreg.QueryValueEx(k, name)[0]
        return not (data and data[0] & 1)  # odd first byte = disabled
    except OSError:
        return True

def entries():
    out = []
    for scope, root, where, sub in SOURCES:
        if sub == "StartupFolder":
            items = [(f, os.path.join(where, f)) for f in os.listdir(where) if f.lower() != "desktop.ini"] \
                if os.path.isdir(where) else []
            for name, path in items:
                out.append({"name": os.path.splitext(name)[0], "value": name, "command": path, "target": path,
                            "scope": scope, "root": root, "where": where, "sub": sub,
                            "enabled": _enabled(root, sub, name)})
        else:
            for name, cmd in values(root, where).items():
                out.append({"name": name, "value": name, "command": cmd, "target": _target(cmd), "scope": scope,
                            "root": root, "where": where, "sub": sub, "enabled": _enabled(root, sub, name)})
    return sorted(out, key=lambda e: e["name"].lower())

def set_enabled(e, on):
    data = b"\x02" + b"\0" * 11 if on else b"\x03\0\0\0" + struct.pack("<Q", int((time.time() + 11644473600) * 1e7))
    with winreg.CreateKeyEx(e["root"], f"{APPROVED}\\{e['sub']}", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, e["value"], 0, winreg.REG_BINARY, data)
    e["enabled"] = on

def remove(e):
    """Deletes the entry for good (the shortcut goes to the Recycle Bin)."""
    if e["sub"] == "StartupFolder":
        send2trash(e["command"])
    else:
        with winreg.OpenKey(e["root"], e["where"], 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, e["value"])

def add(path, name=None):
    """Start an app when you sign in (current user)."""
    name = name or os.path.splitext(os.path.basename(path))[0]
    with winreg.CreateKeyEx(HKCU, RUN, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, f'"{path}"')
