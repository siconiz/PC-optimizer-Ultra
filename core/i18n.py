"""Tiny translation layer: t("English text") returns the Korean text when the UI language is Korean."""
import ctypes
from .lang_ko import KO

LANG = ["en"]

def init(pref="auto"):
    if pref == "auto":
        try:
            pref = "ko" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x12 else "en"
        except Exception:
            pref = "en"
    LANG[0] = pref
    return pref

def t(text, /, **kw):
    if LANG[0] == "ko":
        text = KO.get(text, text)
    return text.format(**kw) if kw else text
