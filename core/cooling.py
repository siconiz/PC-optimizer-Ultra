"""Cooling: Windows system cooling policy and power mode. Direct fan control needs vendor tools (see UI)."""
import ctypes, re, uuid
from .gpuinfo import GUID
from .power import pc

SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00"
SYSCOOLPOL = "94d3a615-a899-4ac5-ae2b-e4d8f634367f"
MODES = {"Best power efficiency": "961cc777-2547-4f9d-8174-7d86181b8a7a",
         "Balanced": "00000000-0000-0000-0000-000000000000",
         "Best performance": "ded574b5-45a0-4f42-8737-46345c09c238"}

def cooling_policy():
    """(ac, dc): 1 = active (fan first), 0 = passive (slow the CPU first), None = unknown."""
    vals = re.findall(r"0x([0-9a-fA-F]{8})", pc("/q", "SCHEME_CURRENT", SUB_PROCESSOR, SYSCOOLPOL))
    return (int(vals[-2], 16), int(vals[-1], 16)) if len(vals) >= 2 else (None, None)

def set_cooling_policy(active):
    v = str(int(active))
    pc("/setacvalueindex", "SCHEME_CURRENT", SUB_PROCESSOR, SYSCOOLPOL, v)
    pc("/setdcvalueindex", "SCHEME_CURRENT", SUB_PROCESSOR, SYSCOOLPOL, v)
    pc("/setactive", "SCHEME_CURRENT")

def _guid(s):
    b = uuid.UUID(s).bytes_le
    return GUID.from_buffer_copy(b)

def power_mode():
    try:
        g = GUID()
        if ctypes.windll.powrprof.PowerGetEffectiveOverlayScheme(ctypes.byref(g)) == 0:
            cur = str(uuid.UUID(bytes_le=bytes(g)))
            return next((k for k, v in MODES.items() if v == cur), None)
    except (AttributeError, OSError):
        pass
    return None

def set_power_mode(name):
    f = ctypes.windll.powrprof.PowerSetActiveOverlayScheme
    f.argtypes = [GUID]
    return f(_guid(MODES[name])) == 0
