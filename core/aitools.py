"""Local AI helpers: Ollama loaded models (API), VRAM per process (PDH), model memory estimate, keep-alive."""
import json, re, urllib.request
import psutil
from .reg import HKCU, delete, get, set_value

OLLAMA = "http://127.0.0.1:11434"
ENV = "Environment"
AI_EXES = {"ollama.exe", "ollama app.exe", "lm studio.exe", "lms.exe", "koboldcpp.exe", "llama-server.exe",
           "jan.exe", "gpt4all.exe", "comfyui.exe"}

def _api(path, body=None):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read() or b"{}")

def ollama_models():
    """Models Ollama has in memory now: name, total GB, GB in VRAM."""
    return [{"name": m["name"], "gb": round(m["size"] / 2**30, 1), "vram_gb": round(m.get("size_vram", 0) / 2**30, 1)}
            for m in _api("/api/ps").get("models", [])]

def ollama_unload(name):
    _api("/api/generate", {"model": name, "keep_alive": 0})  # Ollama FAQ: keep_alive 0 unloads at once

def keep_alive():
    return get(HKCU, ENV, "OLLAMA_KEEP_ALIVE")

def set_keep_alive(value):
    """'1m', '5m' (Ollama default), '30m', '-1' (forever). None restores the default. Restart Ollama to apply."""
    delete(HKCU, ENV, "OLLAMA_KEEP_ALIVE") if value is None else set_value(HKCU, ENV, "OLLAMA_KEEP_ALIVE", value)

def vram_by_process():
    """[(name, pid, MB of dedicated VRAM)] largest first, from 'GPU Process Memory' counters."""
    import win32pdh
    _, instances = win32pdh.EnumObjectItems(None, None, "GPU Process Memory", win32pdh.PERF_DETAIL_WIZARD)
    q = win32pdh.OpenQuery()
    hs = [(i, win32pdh.AddEnglishCounter(q, rf"\GPU Process Memory({i})\Dedicated Usage")) for i in set(instances)]
    win32pdh.CollectQueryData(q)
    per = {}
    for inst, h in hs:
        m = re.match(r"pid_(\d+)_", inst)
        if m:
            try:
                per[int(m.group(1))] = per.get(int(m.group(1)), 0) + win32pdh.GetFormattedCounterValue(
                    h, win32pdh.PDH_FMT_LARGE)[1]
            except Exception:
                pass
    win32pdh.CloseQuery(q)
    out = []
    for pid, b in per.items():
        if b > 50 * 2**20:
            try:
                out.append((psutil.Process(pid).name(), pid, round(b / 2**20)))
            except (psutil.Error, OSError):
                pass
    return sorted(out, key=lambda x: -x[2])

def estimate(params_b, bits, ctx_k):
    """Rough memory need in GB: weights (params x bits / 8) + KV cache + about 10% runtime overhead.
    KV cache uses ~0.125 GB per 1K tokens for an 8B model with grouped-query attention (FP16), scaled by size."""
    weights = params_b * bits / 8
    kv = 0.125 * ctx_k * max(0.5, (params_b / 8) ** 0.5)
    return round(weights * 1.1 + kv, 1)
