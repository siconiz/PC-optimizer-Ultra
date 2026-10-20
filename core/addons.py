"""Optional downloads: extra dashboard widgets and fonts, fetched only when the user asks for them.

Every file must match the SHA-256 built into this app version, so a changed or tampered file on the server is
refused. Widget files come from this project's repository; fonts from their authors' repositories (pinned commit)."""
import hashlib, os, types, urllib.request
from .version import REPO

WIDGET_URL = f"https://raw.githubusercontent.com/{REPO}/main/widgets/{{file}}"
PRETENDARD = ("https://raw.githubusercontent.com/orioncactus/pretendard/7aeb0698819be2b4097dae8ec8fe6a795e5cf3ae/"
              "examples/flutter_pretendard/fonts/{file}")
BASE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "PCOptimizer")
CATALOG = {  # id: title, kind, [(file, url or None for this repo, sha256)], extra
    "wallpaper": {"title": "Wallpaper", "kind": "widget",
                  "files": [("wallpaper.py", None, "c9d4e132d0c8a74f24908f1ec8879804058008988633ab3febdc9ad9b95414ed")]},
    "display": {"title": "Display", "kind": "widget",
                "files": [("display.py", None, "f0c090199132a63f8c51f7d6a5e3956294b2e45596032533a34f28f6ff2a172e")]},
    "audio": {"title": "Audio", "kind": "widget",
              "files": [("audio.py", None, "0f44090638ca34474dde5087cf37ebb3eb6d4511aefe6e865b2795ead5026618")]},
    "input": {"title": "Mouse & keyboard", "kind": "widget",
              "files": [("input.py", None, "6a2eab2a30a5e0da13e814cce7b2618bfbad3e40df353b1a510450dfd575bb35")]},
    "pretendard": {"title": "Pretendard font", "kind": "font", "family": "Pretendard", "license": "SIL OFL 1.1",
                   "files": [("Pretendard-Regular.otf", PRETENDARD,
                              "3ffbacde6ab8411f1d2db54bb9b1f0b3ee2a738932033722cf0388c06aed1c93"),
                             ("Pretendard-Bold.otf", PRETENDARD,
                              "2e91915fab54df71cc9598ebf608b2bdb54c6fe3c066ac61dff0bc44fca71cc7")]},
}

def ids(kind):
    return [k for k, v in CATALOG.items() if v["kind"] == kind]

def _dir(aid):
    return os.path.join(BASE, "widgets" if CATALOG[aid]["kind"] == "widget" else "fonts")

def _norm(name, data):
    # text files: same fingerprint whether git checked them out with CRLF or LF
    return data.replace(b"\r\n", b"\n") if name.endswith(".py") else data

def _ok(name, data, sha):
    return hashlib.sha256(_norm(name, data)).hexdigest() == sha

def _read(aid, name):
    with open(os.path.join(_dir(aid), name), "rb") as f:
        return f.read()

def installed(aid):
    try:
        return all(_ok(n, _read(aid, n), sha) for n, _, sha in CATALOG[aid]["files"])
    except OSError:
        return False

def _bundled(name):
    """Copy of the widget shipped inside the app (same fingerprint), used when GitHub cannot be reached or the
    file is not published there yet."""
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for p in (os.path.join(base, "widgets", name), os.path.join(base, "assets", "widgets", name)):
        if os.path.isfile(p):
            with open(p, "rb") as f:
                return f.read()
    return None

def download(aid):
    got = []
    for name, url, sha in CATALOG[aid]["files"]:
        data, err = None, ""
        try:
            req = urllib.request.Request((url or WIDGET_URL).format(file=name),
                                         headers={"User-Agent": "PCOptimizer/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if not _ok(name, data, sha):
                data, err = None, "checksum"
        except Exception as e:  # offline, blocked, or not on GitHub (404)
            err = str(e)
        if data is None and url is None:
            data = _bundled(name)
            if data is not None and not _ok(name, data, sha):
                data = None
        if data is None:
            raise RuntimeError(err or "download failed")
        got.append((name, data))
    os.makedirs(_dir(aid), exist_ok=True)
    for name, data in got:  # write only after every file passed the check
        with open(os.path.join(_dir(aid), name), "wb") as f:
            f.write(data)

def load(aid):
    """Runs a verified widget file; it provides build(app, body)."""
    name, _, sha = CATALOG[aid]["files"][0]
    data = _read(aid, name)
    if not _ok(name, data, sha):
        raise RuntimeError("checksum")
    mod = types.ModuleType(f"pco_widget_{aid}")
    exec(compile(_norm(name, data), os.path.join(_dir(aid), name), "exec"), mod.__dict__)  # exactly the verified bytes
    return mod

def remove(aid):
    for name, _, _ in CATALOG[aid]["files"]:
        try:
            os.remove(os.path.join(_dir(aid), name))
        except OSError:
            pass
