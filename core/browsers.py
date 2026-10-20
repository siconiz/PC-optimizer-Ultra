"""Browser cache cleanup and Microsoft Edge removal."""
import glob, os, re, shutil, subprocess
import psutil
from .cleaner import _dir_size
from .i18n import t

LOCAL = os.environ.get("LOCALAPPDATA", "")
CHROMIUM = {"Chrome": (r"Google\Chrome\User Data", "chrome.exe"),
            "Edge": (r"Microsoft\Edge\User Data", "msedge.exe"),
            "Whale": (r"Naver\Naver Whale\User Data", "whale.exe"),
            "Brave": (r"BraveSoftware\Brave-Browser\User Data", "brave.exe")}
CACHE_DIRS = ("Cache", "Code Cache", "GPUCache")
EDGE_SETUP = r"%ProgramFiles(x86)%\Microsoft\Edge\Application\*\Installer\setup.exe"
EDGE_STUB = r"%SystemRoot%\SystemApps\Microsoft.MicrosoftEdge_8wekyb3d8bbwe\MicrosoftEdge.exe"

def running(exe):
    return any((p.info["name"] or "").lower() == exe for p in psutil.process_iter(["name"]))

def browsers():
    out = []
    for name, (rel, exe) in CHROMIUM.items():
        root = os.path.join(LOCAL, rel)
        if os.path.isdir(root):
            dirs = [d for prof in glob.glob(os.path.join(root, "*")) for c in CACHE_DIRS
                    if os.path.isdir(d := os.path.join(prof, c))]
            out.append({"name": name, "exe": exe, "dirs": dirs})
    ff = os.path.join(LOCAL, r"Mozilla\Firefox\Profiles")
    if os.path.isdir(ff):
        out.append({"name": "Firefox", "exe": "firefox.exe", "dirs": glob.glob(os.path.join(ff, "*", "cache2"))})
    for b in out:
        b["size_mb"] = round(sum(_dir_size(d) for d in b["dirs"]) / 2**20)
        b["running"] = running(b["exe"])
    return out

def clear_cache(b):
    """Deletes only cache folders (not history, cookies, passwords or bookmarks)."""
    if running(b["exe"]):
        raise RuntimeError(t("Close {name} first (check the system tray too).", name=b["name"]))
    for d in b["dirs"]:
        shutil.rmtree(d, ignore_errors=True)

def _edge_setups():
    def ver(p):
        return tuple(int(x) for x in re.findall(r"\d+", p.split("\\Application\\")[-1].split("\\")[0]))
    return sorted(glob.glob(os.path.expandvars(EDGE_SETUP)), key=ver)

def edge_installed():
    return bool(_edge_setups())

def remove_edge():
    """Same method as Chris Titus WinUtil. WebView2 (used by other apps) is not removed."""
    setups = _edge_setups()
    if not setups:
        return True
    try:
        stub = os.path.expandvars(EDGE_STUB)
        os.makedirs(os.path.dirname(stub), exist_ok=True)
        open(stub, "a").close()
    except OSError:
        pass
    subprocess.run([setups[-1], "--uninstall", "--system-level", "--force-uninstall", "--delete-profile"],
                   capture_output=True, timeout=900, creationflags=0x08000000)
    return not edge_installed()

def reinstall_edge():
    from .apps import _winget
    return _winget("install", "--id", "Microsoft.Edge", "--exact", "--source", "winget")
