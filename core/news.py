"""Background news feeds: Windows 11 Widgets, Windows 10 News and interests, Edge new tab news (all policies)."""
from .reg import HKLM, delete, get, set_value

POLICIES = [(HKLM, r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests"),          # Windows 11 Widgets
            (HKLM, r"SOFTWARE\Policies\Microsoft\Windows\Windows Feeds", "EnableFeeds"),   # Windows 10
            (HKLM, r"SOFTWARE\Policies\Microsoft\Edge", "NewTabPageContentEnabled")]       # Edge new tab content

def is_off():
    return all(get(*p) == 0 for p in POLICIES)

def set_off(off):
    """off=True writes the policies (0); False removes them so Windows' defaults return. Takes effect after
    sign-out (Widgets / News) or an Edge restart."""
    for p in POLICIES:
        set_value(*p, 0) if off else delete(*p)
