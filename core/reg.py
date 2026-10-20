import winreg

HKCU, HKLM = winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE

def get(root, path, name, default=None):
    try:
        with winreg.OpenKey(root, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default

def set_value(root, path, name, value):
    kind = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
    with winreg.CreateKeyEx(root, path, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, kind, value)

def delete(root, path, name):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except OSError:
        pass

def values(root, path):
    out = {}
    try:
        with winreg.OpenKey(root, path) as k:
            i = 0
            while True:
                n, v, _ = winreg.EnumValue(k, i)
                out[n] = v
                i += 1
    except OSError:
        pass
    return out
