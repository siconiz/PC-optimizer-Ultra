"""Extract a file's icon as a PIL image (cached as PNG). Uses only ctypes + GDI."""
import ctypes, hashlib, os
from ctypes import wintypes
from PIL import Image

CACHE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "PCOptimizer", "icons")

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

def _hicon_to_image(hicon, size):
    gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
    for f in (gdi.CreateCompatibleDC, gdi.CreateDIBSection, gdi.SelectObject):
        f.restype = ctypes.c_void_p
    gdi.SelectObject.argtypes = gdi.DeleteObject.argtypes = None
    user.DrawIconEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wintypes.HICON, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hdc = gdi.CreateCompatibleDC(None)
    hbmp = gdi.CreateDIBSection(ctypes.c_void_p(hdc), ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    old = gdi.SelectObject(ctypes.c_void_p(hdc), ctypes.c_void_p(hbmp))
    user.DrawIconEx(hdc, 0, 0, hicon, size, size, 0, None, 3)  # DI_NORMAL
    raw = ctypes.string_at(bits, size * size * 4)
    gdi.SelectObject(ctypes.c_void_p(hdc), ctypes.c_void_p(old))
    gdi.DeleteObject(ctypes.c_void_p(hbmp))
    gdi.DeleteDC(ctypes.c_void_p(hdc))
    return Image.frombuffer("RGBA", (size, size), raw, "raw", "BGRA", 0, 1)

def icon(path, index=0, size=32):
    """PIL image of the icon in an exe/dll/ico, or None."""
    if not path or not os.path.exists(path):
        return None
    key = hashlib.md5(f"{path.lower()}|{index}|{size}".encode()).hexdigest()
    cached = os.path.join(CACHE, key + ".png")
    if os.path.exists(cached):
        try:
            return Image.open(cached)
        except OSError:
            pass
    hicon = wintypes.HICON()
    shell = ctypes.windll.shell32
    if shell.SHDefExtractIconW(path, index, 0, ctypes.byref(hicon), None, size) != 0 or not hicon:
        return None
    try:
        img = _hicon_to_image(hicon, size)
    finally:
        ctypes.windll.user32.DestroyIcon(hicon)
    os.makedirs(CACHE, exist_ok=True)
    img.save(cached)
    return img
