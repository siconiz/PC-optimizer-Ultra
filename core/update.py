"""Checks GitHub Releases for a newer version. Sends no user data, only a plain HTTPS GET."""
import json, re, urllib.request
from .version import __version__, REPO

def _parse(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])

def newer_release():
    """(tag, url) when a newer release exists, else None."""
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "PCOptimizer"})
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    return (tag, data.get("html_url")) if _parse(tag) > _parse(__version__) else None
