"""AI suggestions for the cleanup list. Only short file facts are sent: name, kind, size and age. File contents
and folder paths are never sent. Ollama runs on this PC; Claude uses the user's own API key, stored encrypted for
this Windows user (DPAPI)."""
import base64, json, os, urllib.request

CLAUDE_URL, CLAUDE_MODEL, CLAUDE_VERSION = "https://api.anthropic.com/v1/messages", "claude-haiku-5-5", "2026-10-21"
OLLAMA = "http://127.0.0.1:11434"
PROMPT = ("You help clean up a Windows PC. The JSON list below has one entry per file or folder: id, name, kind, "
          "size_mb, age_days. Pick the entries that are most likely safe and worth moving to the Recycle Bin "
          "(old installers, temp and cache files, duplicates such as 'name (1).ext', forgotten large downloads). "
          "Be careful with personal photos, videos, documents and game saves: pick them only when they look like "
          "copies or leftovers. Answer with JSON only: {\"pick\": [{\"id\": 0, \"why\": \"short reason\"}]}. "
          "Write the reasons in LANG.\n")

def facts(cands, limit=300):
    """The largest `limit` candidates and what is sent about them (no folder paths)."""
    rows = sorted(cands, key=lambda x: -x["size_mb"])[:limit]
    return rows, [{"id": i, "name": os.path.basename(x["path"].rstrip("\\/")), "kind": x["kind"],
                   "size_mb": x["size_mb"], "age_days": x["age_days"]} for i, x in enumerate(rows)]

def save_key(cfg, key):
    import win32crypt
    cfg["ai_key"] = base64.b64encode(win32crypt.CryptProtectData(key.strip().encode(), "PCOptimizer", None, None,
                                                                 None, 0)).decode() if key.strip() else None

def _key(cfg):
    import win32crypt
    return win32crypt.CryptUnprotectData(base64.b64decode(cfg["ai_key"]), None, None, None, 0)[1].decode()

def _post(url, body, headers, timeout=120):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def _ollama(prompt):
    with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as r:
        models = [m["name"] for m in json.loads(r.read()).get("models", [])]
    if not models:
        raise RuntimeError("Ollama has no model. Run: ollama pull llama3.2")
    out = _post(OLLAMA + "/api/chat", {"model": models[0], "stream": False, "format": "json",
                                       "messages": [{"role": "user", "content": prompt}]}, {}, 300)
    return out["message"]["content"]

def _claude(cfg, prompt):
    out = _post(CLAUDE_URL, {"model": CLAUDE_MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]},
                {"x-api-key": _key(cfg), "anthropic-version": CLAUDE_VERSION})
    return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")

def suggest(cfg, cands, provider, lang):
    """[(path, reason)] picked by the AI from the candidates."""
    rows, data = facts(cands)
    prompt = PROMPT.replace("LANG", "Korean" if lang == "ko" else "English") + json.dumps(data, ensure_ascii=False)
    text = _ollama(prompt) if provider == "ollama" else _claude(cfg, prompt)
    picks = json.loads(text[text.index("{"): text.rindex("}") + 1]).get("pick", [])
    return [(rows[p["id"]]["path"], str(p.get("why", ""))[:120]) for p in picks
            if isinstance(p, dict) and isinstance(p.get("id"), int) and 0 <= p["id"] < len(rows)]
