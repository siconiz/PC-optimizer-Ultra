"""Downloadable dashboard widget: AI assistant. Pop-ups when an AI asks you something (Claude Code hooks or any
program through a local address), API keys, a quick chat window, a prompt builder and a project packer for vibe
coding. Provides build(app, body)."""
import base64, fnmatch, json, os, secrets, threading, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import customtkinter as ctk
from core.i18n import t
from ui.theme import ACCENT, BG, CARD, CARD2, HOVER2, MUTED, TEXT, WARN

PORT = 47821
CLAUDE_VERSION = "2026-10-21"
PROVIDERS = {"anthropic": ("Claude (Anthropic)", "ANTHROPIC_API_KEY"), "openai": ("OpenAI", "OPENAI_API_KEY"),
             "gemini": ("Gemini (Google)", "GEMINI_API_KEY")}

def _menu(parent, values, width=220, command=None):
    return ctk.CTkOptionMenu(parent, values=values or ["-"], width=width, height=30, fg_color=CARD2,
                             button_color=CARD2, button_hover_color=HOVER2, command=command,
                             dynamic_resizing=False)  # long model names must not push the other buttons out

def _http(url, body=None, headers=None, timeout=120, method=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {"content-type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:  # show the service's own message, not just the status
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None

# ---------- API keys (encrypted for this Windows user with DPAPI) ----------
def save_key(cfg, prov, key):
    import win32crypt
    keys = cfg.setdefault("keys", {})
    if key.strip():
        keys[prov] = base64.b64encode(win32crypt.CryptProtectData(key.strip().encode(), "PCOptimizer", None, None,
                                                                  None, 0)).decode()
    else:
        keys.pop(prov, None)

def get_key(cfg, prov):
    import win32crypt
    k = cfg.get("keys", {}).get(prov)
    return win32crypt.CryptUnprotectData(base64.b64decode(k), None, None, None, 0)[1].decode() if k else None

def set_env_key(cfg, prov, on):
    """Puts the key in the user environment (ANTHROPIC_API_KEY ...) so coding tools started later find it."""
    import ctypes
    from core.reg import HKCU, delete, set_value
    name = PROVIDERS[prov][1]
    set_value(HKCU, "Environment", name, get_key(cfg, prov)) if on else delete(HKCU, "Environment", name)
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 2, 3000, None)

def list_models(cfg, prov):
    """Model ids the key can use (also the key test)."""
    k = get_key(cfg, prov)
    if prov == "anthropic":
        r = _http("https://api.anthropic.com/v1/models?limit=100", headers={
            "Authorization": "Bearer " + k, "anthropic-version": CLAUDE_VERSION}, method="GET")
        return [m["id"] for m in r.get("data", [])]
    if prov == "openai":
        r = _http("https://api.openai.com/v1/models", headers={"Authorization": "Bearer " + k}, method="GET")
        return sorted(m["id"] for m in r.get("data", []))
    r = _http("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200&key=" + urllib.parse.quote(k),
              method="GET")
    return [m["name"].split("/", 1)[1] for m in r.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]

def ollama_models():
    try:
        return [m["name"] for m in _http("http://127.0.0.1:11434/api/tags", timeout=3, method="GET")["models"]]
    except Exception:
        return []

def chat(cfg, prov, model, messages):
    """One answer. messages: [{'role': 'user'|'assistant', 'content': str}]"""
    if prov == "ollama":
        return _http("http://127.0.0.1:11434/api/chat", {"model": model, "messages": messages, "stream": False},
                     timeout=600)["message"]["content"]
    k = get_key(cfg, prov)
    if prov == "anthropic":
        r = _http("https://api.anthropic.com/v1/messages", {"model": model, "max_tokens": 4096, "messages": messages},
                  {"Authorization": "Bearer " + k, "anthropic-version": CLAUDE_VERSION})
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
    if prov == "openai":
        r = _http("https://api.openai.com/v1/chat/completions", {"model": model, "messages": messages},
                  {"Authorization": "Bearer " + k})
        return r["choices"][0]["message"]["content"]
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages]
    r = _http(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key="
              + urllib.parse.quote(k), {"contents": contents})
    return "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])

def tokens(text):
    """Rough token count (no exact count without the model's tokenizer): ~4 characters per token in English,
    ~1.5 in Korean."""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    return round(hangul / 1.5 + (len(text) - hangul) / 4)

# ---------- AI requests: pop-ups and the local address ----------
class Popup:
    """Small always-on-top window for one request. done(answer) gets {'choice', 'text'} or None (closed / timeout)."""
    open_count = 0

    def __init__(self, app, title, message, detail="", buttons=(("ok", "OK"),), ask_text=False, timeout=120,
                 done=None, on_button=None):
        self.app, self.done, self.answered, self.left = app, done, False, timeout
        w = self.w = ctk.CTkToplevel(app, fg_color=BG)
        w.title(title)
        w.attributes("-topmost", True)
        w.attributes("-alpha", app.cfg.get("assistant", {}).get("popup_alpha", 0.97))
        w.resizable(False, False)
        Popup.open_count += 1
        n = Popup.open_count
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"420x{300 if detail else 190}+{sw - 440}+{max(20, sh - 360 - (n - 1) * 40)}")
        w.protocol("WM_DELETE_WINDOW", lambda: self.finish(None))
        box = ctk.CTkFrame(w, fg_color=CARD, corner_radius=12, border_width=2, border_color=ACCENT)
        box.pack(fill="both", expand=True, padx=8, pady=8)
        app.label(box, title, 14, bold=True, wrap=380).pack(anchor="w", padx=12, pady=(10, 2))
        if message:
            app.label(box, message, 12, muted=True, wrap=380).pack(anchor="w", padx=12)
        if detail:
            d = ctk.CTkTextbox(box, height=90, fg_color=CARD2, font=("Consolas", 12), wrap="word")
            d.insert("1.0", detail)
            d.configure(state="disabled")
            d.pack(fill="x", padx=12, pady=(6, 0))
        self.entry = None
        if ask_text:
            self.entry = ctk.CTkEntry(box, height=30, placeholder_text=t("Reason or answer (optional)"))
            self.entry.pack(fill="x", padx=12, pady=(6, 0))
        r = ctk.CTkFrame(box, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=10)
        for i, (key, label) in enumerate(buttons):
            app.button(r, label, lambda k=key: (on_button(k) if on_button else None, self.finish(k)),
                       primary=i == 0, width=90).pack(side="left", padx=(0, 6))
        self.count = app.label(r, "", 11, muted=True)
        self.count.pack(side="right")
        try:
            import winsound
            winsound.MessageBeep(0x40)  # MB_ICONASTERISK
        except Exception:
            pass
        w.lift()
        w.focus_force()
        self.tick()

    def tick(self):
        if self.answered:
            return
        if self.left <= 0:
            return self.finish(None)
        self.count.configure(text=t("{s} s", s=self.left))
        self.left -= 1
        self.w.after(1000, self.tick)

    def finish(self, choice):
        if self.answered:
            return
        self.answered = True
        text = self.entry.get().strip() if self.entry else ""
        Popup.open_count = max(0, Popup.open_count - 1)
        self.w.destroy()
        if self.done:
            self.done({"choice": choice, "text": text} if choice else None)

class Requests:
    """Local address (127.0.0.1 only, token required) that turns requests into pop-ups:
    POST /claude/permission  Claude Code PermissionRequest hook -> allow / deny
    POST /claude/notify      Claude Code Notification hook (waiting for input, finished ...)
    POST /ask                any program: {"title", "message", "detail", "options": [...], "input": bool, "timeout"}
                             -> {"answer": option or null, "text": "..."}"""
    def __init__(self, app):
        self.app, self.cfg = app, app.cfg.setdefault("assistant", {})
        self.cfg.setdefault("token", secrets.token_urlsafe(24))
        self.srv, self.error = None, None

    @property
    def base(self):
        return f"http://127.0.0.1:{self.cfg.get('port', PORT)}"

    def start(self):
        me = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, obj=None):
                b = json.dumps(obj, ensure_ascii=False).encode() if obj is not None else b""
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                self.reply(200, {"ok": True}) if self.path == "/health" else self.reply(404)

            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer " + me.cfg["token"]:
                    return self.reply(401, {"error": "bad token"})
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                except ValueError:
                    return self.reply(400, {"error": "bad json"})
                fn = {"/claude/permission": me.permission, "/claude/notify": me.notify,
                      "/ask": me.ask}.get(self.path.split("?")[0])
                self.reply(200, fn(body)) if fn else self.reply(404)
        try:
            self.srv = ThreadingHTTPServer(("127.0.0.1", self.cfg.get("port", PORT)), Handler)
            threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        except OSError as e:
            self.error = str(e)

    def _wait(self, timeout, **kw):
        """Shows a pop-up on the UI thread and waits here (server thread) for the answer."""
        ev, box = threading.Event(), {}
        def done(a):
            box["a"] = a
            ev.set()
        self.app.ui(lambda: Popup(self.app, timeout=timeout, done=done, **kw))
        ev.wait(timeout + 10)
        return box.get("a")

    def permission(self, body):
        ti = body.get("tool_input") or {}
        detail = ti.get("command") or ti.get("file_path") or ti.get("url") or json.dumps(
            ti, ensure_ascii=False, indent=1)[:2000]
        a = self._wait(self.cfg.get("timeout", 120), title=t("Claude Code asks to use {tool}",
                       tool=body.get("tool_name", "?")), message=t("Folder: {d}", d=body.get("cwd", "")),
                       detail=detail, buttons=(("allow", t("Allow")), ("deny", t("Deny"))), ask_text=True)
        if not a:
            return None  # empty reply: Claude Code shows its own prompt as usual
        if a["choice"] == "allow":
            return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
        return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {
            "behavior": "deny", "message": a["text"] or "Denied by the user."}}}

    def notify(self, body):
        self.app.ui(lambda: Popup(self.app, body.get("title") or "Claude Code", body.get("message", ""),
                                  buttons=(("show", t("Show")), ("close", t("Close"))), timeout=30,
                                  on_button=lambda k: k == "show" and _front("claude")))
        return None

    def ask(self, body):
        opts = [str(o) for o in body.get("options") or ["OK"]][:4]
        a = self._wait(int(body.get("timeout") or 120), title=str(body.get("title") or t("AI request")),
                       message=str(body.get("message") or ""), detail=str(body.get("detail") or ""),
                       buttons=[(o, o) for o in opts], ask_text=bool(body.get("input")))
        return {"answer": a and a["choice"], "text": a and a["text"]}

def _front(word):
    """Brings the first visible window whose title contains `word` to the front."""
    import win32con, win32gui
    found = []
    win32gui.EnumWindows(lambda h, _: found.append(h) if win32gui.IsWindowVisible(h) and
                         word in win32gui.GetWindowText(h).lower() else None, None)
    if found:
        win32gui.ShowWindow(found[0], win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(found[0])

# ---------- Claude Code connection (user settings, hooks reload without a restart) ----------
def claude_settings():
    root = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(root, "settings.json")

def _ours(group, base):
    return any(str(h.get("url", "")).startswith(base) for h in group.get("hooks", []))

def claude_connected(req):
    try:
        with open(claude_settings(), encoding="utf-8") as f:
            hooks = json.load(f).get("hooks", {})
    except (OSError, ValueError):
        return False
    return any(_ours(g, req.base) for g in hooks.get("PermissionRequest", []))

def claude_connect(req, on):
    """Adds (or removes) our two HTTP hooks in ~/.claude/settings.json; other settings stay as they are."""
    path = claude_settings()
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)  # stop on a broken file instead of overwriting it
        backup = path + ".pco-backup"
        if not os.path.exists(backup):
            with open(backup, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    hooks = data.setdefault("hooks", {})
    for ev in ("PermissionRequest", "Notification"):
        hooks[ev] = [g for g in hooks.get(ev, []) if not _ours(g, req.base)]
    auth = {"Authorization": "Bearer " + req.cfg["token"]}
    if on:
        hooks["PermissionRequest"].append({"hooks": [{"type": "http", "url": req.base + "/claude/permission",
                                                      "timeout": req.cfg.get("timeout", 120) + 15, "headers": auth}]})
        hooks["Notification"].append({"matcher": "idle_prompt|agent_needs_input|elicitation_dialog|agent_completed",
                                      "hooks": [{"type": "http", "url": req.base + "/claude/notify", "timeout": 10,
                                                 "headers": auth}]})
    for ev in ("PermissionRequest", "Notification"):
        if not hooks[ev]:
            del hooks[ev]
    if not hooks:
        del data["hooks"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------- prompt builder (rules, nothing is sent anywhere) ----------
VAGUE = ("better", "nice", "good", "properly", "something", "stuff", "etc", "잘", "좋게",
         "알아서", "적당히", "대충")  # Korean: well, nicely, on your own, roughly

def build_prompt(f):
    parts = [("Role", f["role"]), ("Goal", f["goal"]), ("Context", f["context"]), ("Constraints", f["rules"]),
             ("Output format", f["format"]), ("Example", f["example"])]
    text = "\n\n".join(f"# {h}\n{v.strip()}" for h, v in parts if v.strip())
    if f.get("ask"):
        text += "\n\nIf anything is unclear, ask me questions before you start."
    return text

def check_prompt(f):
    """Short list of what is missing, from common prompt guidelines (goal, context, format, examples)."""
    out, goal = [], f["goal"].strip()
    if not goal:
        out.append(t("Write the goal: what should the AI produce?"))
    elif len(goal) < 15:
        out.append(t("The goal is very short: say what, for whom and how much."))
    if not f["context"].strip():
        out.append(t("Add context: the situation, the audience or the code it belongs to."))
    if not f["format"].strip():
        out.append(t("Say the output format: list, table, code only, length..."))
    if not f["example"].strip():
        out.append(t("An example of a good answer helps a lot."))
    low = " ".join(str(v) for v in f.values()).lower()
    if any(w in low.split() for w in VAGUE):
        out.append(t("Replace vague words (better, nice, properly...) with something you can check."))
    return out or [t("Looks complete.")]

# ---------- project packer for vibe coding ----------
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next", "target", "bin", "obj",
             ".idea", ".vs", ".gradle", ".expo", "coverage", ".mypy_cache", ".pytest_cache"}
SECRET = ("*.env", ".env*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*secret*", "*credential*", "*.keystore")
CODE_EXT = ".py .js .ts .tsx .jsx .json .html .css .scss .md .txt .java .kt .c .h .cpp .hpp .cs .go .rs .rb .php " \
           ".swift .sh .ps1 .bat .yml .yaml .toml .ini .xml .sql .vue .svelte .gradle .nsi"

def pack_project(root, exts=CODE_EXT, max_file_kb=200, max_total=400_000):
    """One text with the folder tree and the files' content, ready to paste into a chatbot.
    Leaves out build folders, .gitignore matches, secret-looking files and binaries."""
    want = {e.strip().lower() for e in exts.split()}
    ignore = []
    try:
        with open(os.path.join(root, ".gitignore"), encoding="utf-8", errors="ignore") as f:
            ignore = [ln.strip().rstrip("/") for ln in f if ln.strip() and not ln.startswith(("#", "!"))]
    except OSError:
        pass
    def skipped(rel, name):
        return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p.lstrip("/")) for p in ignore)
    tree, files, left_out = [], [], {"secret": 0, "big": 0, "binary": 0}
    for dirpath, dirs, names in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
                         and not skipped(os.path.normpath(os.path.join(rel_dir, d)).replace("\\", "/"), d))
        depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
        if rel_dir != ".":
            tree.append("  " * (depth - 1) + os.path.basename(dirpath) + "/")
        for n in sorted(names):
            rel = os.path.normpath(os.path.join(rel_dir, n)).replace("\\", "/")
            if skipped(rel, n):
                continue
            tree.append("  " * depth + n)
            p = os.path.join(dirpath, n)
            if any(fnmatch.fnmatch(n.lower(), s) for s in SECRET):
                left_out["secret"] += 1
            elif os.path.splitext(n)[1].lower() in want:
                if os.path.getsize(p) > max_file_kb * 1024:
                    left_out["big"] += 1
                    continue
                with open(p, "rb") as f:
                    raw = f.read()
                if b"\0" in raw[:4096]:
                    left_out["binary"] += 1
                    continue
                files.append((rel, raw.decode("utf-8", "replace")))
    out = [f"Project: {os.path.basename(os.path.abspath(root))}", "", "Folder tree:", *tree, ""]
    size, cut = sum(map(len, out)), 0
    for rel, text in files:
        block = f"=== {rel} ===\n```{os.path.splitext(rel)[1].lstrip('.')}\n{text.rstrip()}\n```\n"
        if size + len(block) > max_total:
            cut += 1
            continue
        out.append(block)
        size += len(block)
    text = "\n".join(out)
    return text, {"files": len(files) - cut, "cut": cut, **left_out, "tokens": tokens(text)}

# ---------- windows ----------
TEMPLATES = {  # shown name: prompt (sent to the AI in English; it answers in the user's language)
    "Explain": "Explain this simply. Answer in the language of the text:\n\n{text}",
    "Fix code": "Find and fix the bugs in this code. Show the corrected code, then a short list of what changed:\n\n{text}",
    "Review code": "Review this code: bugs, security problems, unclear parts. Most important first:\n\n{text}",
    "Translate to Korean": "Translate into natural Korean. Keep code and names as they are:\n\n{text}",
    "Translate to English": "Translate into natural English. Keep code and names as they are:\n\n{text}",
    "Summarize": "Summarize the main points in a short list. Answer in the language of the text:\n\n{text}",
    "Improve my prompt": "Rewrite this prompt so an AI understands it better: clear goal, context, constraints and "
                         "output format. Return only the improved prompt, in the same language:\n\n{text}"}

class ChatWindow:
    """Quick chat with a local Ollama model or an API, in a small window (shortcut)."""
    def __init__(self, app):
        self.app, self.cfg, self.w, self.history = app, app.cfg.setdefault("assistant", {}), None, []

    def toggle(self):
        self.close() if self.w else self.open()

    def open(self, text=None):
        if self.w:
            self.w.lift()
            if text:
                self.input.insert("end", text)
            return
        app = self.app
        w = self.w = ctk.CTkToplevel(app, fg_color=BG)
        w.title(t("Quick chat"))
        w.attributes("-topmost", True)
        w.attributes("-alpha", self.cfg.get("chat_alpha", 1.0))
        w.geometry(self.cfg.get("chat_geo") or f"520x640+{w.winfo_screenwidth() - 560}+60")
        w.protocol("WM_DELETE_WINDOW", self.close)
        top = ctk.CTkFrame(w, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.model = _menu(top, [t("Loading...")], 220, lambda v: self.cfg.__setitem__("chat_model", v))
        self.model.pack(side="left")
        names = {t(k): k for k in TEMPLATES}
        tpl = _menu(top, [t("Template")] + list(names), 130, lambda v: self.use_template(names.get(v)))
        tpl.pack(side="left", padx=6)
        app.button(top, t("New chat"), self.new, primary=False, width=80).pack(side="right")
        self.log = ctk.CTkTextbox(w, fg_color=CARD, wrap="word")
        self.log.pack(fill="both", expand=True, padx=10)
        self.log.configure(state="disabled")
        self.input = ctk.CTkTextbox(w, height=90, fg_color=CARD2, wrap="word")
        self.input.pack(fill="x", padx=10, pady=(6, 0))
        self.input.bind("<Control-Return>", lambda e: (self.send(), "break")[1])
        r = ctk.CTkFrame(w, fg_color="transparent")
        r.pack(fill="x", padx=10, pady=8)
        app.button(r, t("Send (Ctrl+Enter)"), self.send).pack(side="left")
        app.button(r, t("Paste clipboard"), lambda: self.input.insert("end", w.clipboard_get()),
                   primary=False).pack(side="left", padx=6)
        app.button(r, t("Copy answer"), self.copy_last, primary=False).pack(side="left")
        self.status = app.label(r, "", 11, muted=True)
        self.status.pack(side="right")
        self.input.bind("<KeyRelease>", lambda e: self.status.configure(
            text=t("~{n} tokens", n=tokens(self.input.get("1.0", "end")))))
        for m in self.history:
            self.show(m["role"], m["content"])
        if text:
            self.input.insert("end", text)
        app.bg(self.models, self.got_models, lambda m: None)

    def models(self):
        out = ["Ollama: " + m for m in ollama_models()]
        for prov in PROVIDERS:
            if self.cfg.get("keys", {}).get(prov):
                try:
                    ids = list_models(self.cfg, prov)
                except Exception:
                    continue
                out += [f"{prov}: {m}" for m in ids[:40]]
        return out

    def got_models(self, names):
        if not self.w:
            return
        self.model.configure(values=names or [t("No model: install Ollama or add an API key")])
        self.model.set(self.cfg.get("chat_model") if self.cfg.get("chat_model") in names else
                       (names[0] if names else t("No model: install Ollama or add an API key")))

    def use_template(self, key):
        if key:
            text = self.input.get("1.0", "end").strip() or self.w.clipboard_get()
            self.input.delete("1.0", "end")
            self.input.insert("1.0", TEMPLATES[key].format(text=text))

    def show(self, role, text):
        self.log.configure(state="normal")
        self.log.insert("end", ("▶ " if role == "user" else "◆ ") + text.strip() + "\n\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    def send(self):
        text = self.input.get("1.0", "end").strip()
        pick = self.model.get()
        if not text or ": " not in pick:
            return
        prov, model = pick.split(": ", 1)
        prov = "ollama" if prov == "Ollama" else prov
        self.input.delete("1.0", "end")
        self.history.append({"role": "user", "content": text})
        self.show("user", text)
        self.status.configure(text=t("Thinking..."))
        def done(answer):
            self.history.append({"role": "assistant", "content": answer})
            if self.w:
                self.show("assistant", answer)
                self.status.configure(text="")
        def fail(m):
            self.history.pop()
            if self.w:
                self.status.configure(text="")
                self.show("assistant", t("Error: {e}", e=m))
        self.app.bg(lambda: chat(self.cfg, prov, model, list(self.history)), done, fail)

    def copy_last(self):
        last = next((m["content"] for m in reversed(self.history) if m["role"] == "assistant"), "")
        self.w.clipboard_clear()
        self.w.clipboard_append(last)

    def new(self):
        self.history.clear()
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def close(self):
        if self.w:
            self.cfg["chat_geo"] = self.w.geometry()
            self.app.save()
            self.w.destroy()
            self.w = None

def prompt_window(app, chatwin):
    w = ctk.CTkToplevel(app, fg_color=BG)
    w.title(t("Prompt builder"))
    w.geometry("620x720")
    w.attributes("-topmost", True)
    f = ctk.CTkScrollableFrame(w, fg_color="transparent")
    f.pack(fill="both", expand=True, padx=10, pady=10)
    fields = {}
    for key, label, h, hint in (("role", t("Role"), 30, t("e.g. senior Python developer, friendly tutor")),
                                ("goal", t("Goal"), 60, t("What should the AI produce?")),
                                ("context", t("Context"), 80, t("Situation, audience, the code or text it is about")),
                                ("rules", t("Constraints"), 60, t("Must / must not, libraries, length, tone")),
                                ("format", t("Output format"), 40, t("List, table, code only, steps...")),
                                ("example", t("Example"), 60, t("A short example of a good answer (optional)"))):
        app.label(f, label, 13, bold=True).pack(anchor="w", pady=(6, 0))
        app.label(f, hint, 11, muted=True).pack(anchor="w")
        box = ctk.CTkTextbox(f, height=h, fg_color=CARD2, wrap="word")
        box.pack(fill="x")
        fields[key] = box
    ask = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(f, text=t("Ask me questions if anything is unclear"), variable=ask, fg_color=ACCENT,
                    hover_color=ACCENT).pack(anchor="w", pady=8)
    out = ctk.CTkTextbox(f, height=160, fg_color=CARD, wrap="word")
    notes = app.label(f, "", 12, wrap=560)
    def values():
        v = {k: b.get("1.0", "end").strip() for k, b in fields.items()}
        v["ask"] = ask.get()
        return v
    def make():
        v = values()
        text = build_prompt(v)
        out.delete("1.0", "end")
        out.insert("1.0", text)
        notes.configure(text="\n".join("•  " + x for x in check_prompt({k: v[k] for k in fields})) +
                        "\n" + t("~{n} tokens", n=tokens(text)))
        return text
    def copy():
        text = make()
        w.clipboard_clear()
        w.clipboard_append(text)
    r = ctk.CTkFrame(f, fg_color="transparent")
    r.pack(fill="x", pady=(0, 6))
    app.button(r, t("Build and check"), make).pack(side="left")
    app.button(r, t("Copy"), copy, primary=False).pack(side="left", padx=6)
    app.button(r, t("Send to quick chat"), lambda: chatwin.open(make()), primary=False).pack(side="left")
    out.pack(fill="x")
    notes.pack(anchor="w", pady=(6, 0))

def pack_window(app):
    from tkinter import filedialog
    w = ctk.CTkToplevel(app, fg_color=BG)
    w.title(t("Pack a project"))
    w.geometry("560x330")
    w.attributes("-topmost", True)
    f = ctk.CTkFrame(w, fg_color="transparent")
    f.pack(fill="both", expand=True, padx=12, pady=12)
    app.label(f, t("Puts the folder tree and the code files into one text to paste into a chatbot. Build folders, "
                   ".gitignore matches, secret-looking files (.env, keys) and binaries are left out."), 12,
              muted=True, wrap=520).pack(anchor="w")
    app.label(f, t("File types"), 13).pack(anchor="w", pady=(8, 0))
    ext = ctk.CTkEntry(f, height=30)
    ext.insert(0, app.cfg.setdefault("assistant", {}).get("pack_ext", CODE_EXT))
    ext.pack(fill="x")
    msg = app.label(f, "", 12, wrap=520)
    state = {}
    def run():
        folder = filedialog.askdirectory(title=t("Project folder"))
        if not folder:
            return
        app.cfg["assistant"]["pack_ext"] = ext.get()
        msg.configure(text=t("Packing..."), text_color=MUTED)
        def done(res):
            text, s = res
            state["text"] = text
            w.clipboard_clear()
            w.clipboard_append(text)
            msg.configure(text=t("Copied: {f} files, ~{n} tokens. Left out: {s} secret-looking, {b} too big, {x} binary, "
                                 "{c} over the size limit.", f=s["files"], n=s["tokens"], s=s["secret"], b=s["big"],
                                 x=s["binary"], c=s["cut"]), text_color=ACCENT)
        app.bg(lambda: pack_project(folder, ext.get()), done, lambda m: msg.configure(text=m, text_color=WARN))
    def save():
        if state.get("text"):
            p = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")])
            if p:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(state["text"])
    r = ctk.CTkFrame(f, fg_color="transparent")
    r.pack(fill="x", pady=8)
    app.button(r, t("Choose folder and copy"), run).pack(side="left")
    app.button(r, t("Save as .md"), save, primary=False).pack(side="left", padx=6)
    msg.pack(anchor="w")

def settings_window(app, req, chatwin, refresh):
    w = ctk.CTkToplevel(app, fg_color=BG)
    w.title(t("AI assistant settings"))
    w.geometry("640x620")
    w.attributes("-topmost", True)
    f = ctk.CTkScrollableFrame(w, fg_color="transparent")
    f.pack(fill="both", expand=True, padx=10, pady=10)
    c = req.cfg
    # API keys
    app.label(f, t("API keys"), 15, bold=True).pack(anchor="w")
    app.label(f, t("Saved encrypted for this Windows user. Test lists the models the key can use."), 12,
              muted=True, wrap=580).pack(anchor="w")
    for prov, (name, var) in PROVIDERS.items():
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", pady=3)
        app.label(r, name, 13).pack(side="left")
        state = app.label(r, t("Saved") if c.get("keys", {}).get(prov) else t("None"), 12, muted=True)
        state.pack(side="left", padx=8)
        def edit(prov=prov, state=state):
            k = ctk.CTkInputDialog(title=PROVIDERS[prov][0], text=t("Paste the API key (empty: remove)")).get_input()
            if k is not None:
                save_key(c, prov, k)
                app.save()
                state.configure(text=t("Saved") if k.strip() else t("None"), text_color=MUTED)
        def test(prov=prov, state=state):
            if not c.get("keys", {}).get(prov):
                return
            state.configure(text=t("Testing..."))
            app.bg(lambda: list_models(c, prov), lambda ids: state.configure(
                text=t("Works: {n} models", n=len(ids)), text_color=ACCENT),
                   lambda m: state.configure(text=m[:60], text_color=WARN))
        def env(prov=prov, state=state):
            if c.get("keys", {}).get(prov):
                set_env_key(c, prov, True)
                state.configure(text=t("Set as {v}", v=PROVIDERS[prov][1]), text_color=ACCENT)
        app.button(r, t("Environment"), env, primary=False, width=90).pack(side="right")
        app.button(r, t("Test key"), test, primary=False, width=70).pack(side="right", padx=4)
        app.button(r, t("Key..."), edit, primary=False, width=60).pack(side="right")
    app.label(f, t("Environment: saves the key as ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY for your user, so "
                   "coding tools started later use it."), 11, muted=True, wrap=580).pack(anchor="w", pady=(2, 10))
    # requests
    app.label(f, t("AI request pop-ups"), 15, bold=True).pack(anchor="w")
    app.label(f, t("When Claude Code needs your approval, a small window shows what it wants to run and your Allow "
                   "or Deny goes straight back. Without an answer it falls back to the normal prompt in Claude Code."),
              12, muted=True, wrap=580).pack(anchor="w")
    msg = app.label(f, "", 12, wrap=580)
    r = ctk.CTkFrame(f, fg_color="transparent")
    r.pack(fill="x", pady=4)
    def connect(on):
        try:
            claude_connect(req, on)
            msg.configure(text=t("Connected. Claude Code picks it up without a restart.") if on else
                          t("Disconnected."), text_color=ACCENT)
        except Exception as e:
            msg.configure(text=t("Could not change {p}: {e}", p=claude_settings(), e=e), text_color=WARN)
        refresh()
    app.button(r, t("Connect Claude Code"), lambda: connect(True)).pack(side="left")
    app.button(r, t("Disconnect"), lambda: connect(False), primary=False).pack(side="left", padx=6)
    app.button(r, t("Test pop-up"), lambda: Popup(app, t("Test"), t("This is how a request looks."),
                                                  "npm run build", ((("allow", t("Allow")), ("deny", t("Deny")))),
                                                  True, 30), primary=False).pack(side="left")
    msg.pack(anchor="w")
    r = ctk.CTkFrame(f, fg_color="transparent")
    r.pack(fill="x", pady=4)
    app.label(r, t("Wait for an answer"), 13).pack(side="left")
    secs = {t("1 min"): 60, t("2 min"): 120, t("5 min"): 300}
    seg = app.seg(r, list(secs), lambda v: (c.__setitem__("timeout", secs[v]), app.save(),
                                            claude_connected(req) and claude_connect(req, True)))
    seg.set(next((k for k, v in secs.items() if v == c.get("timeout", 120)), t("2 min")))
    seg.pack(side="right")
    def alpha_row(label, key, default, live=None):
        r = ctk.CTkFrame(f, fg_color="transparent")
        r.pack(fill="x", pady=4)
        app.label(r, label, 13).pack(side="left")
        val = app.label(r, "", 12, muted=True)
        val.pack(side="right", padx=(6, 0))
        def move(v):
            c[key] = round(float(v), 2)
            val.configure(text=f"{round(float(v) * 100)}%")
            if live:
                live(c[key])
        sl = ctk.CTkSlider(r, from_=0.3, to=1.0, number_of_steps=14, width=220, command=move)
        sl.set(c.get(key, default))
        sl.pack(side="right")
        sl.bind("<ButtonRelease-1>", lambda e: app.save())
        move(c.get(key, default))
    alpha_row(t("Pop-up opacity"), "popup_alpha", 0.97)
    alpha_row(t("Quick chat opacity"), "chat_alpha", 1.0,
              lambda a: chatwin.w and chatwin.w.attributes("-alpha", a))
    app.label(f, t("Other programs and AIs can ask you too: POST {u}/ask with the header Authorization: Bearer {k} "
                   "and JSON {{\"title\", \"message\", \"options\": [\"Yes\", \"No\"], \"input\": false}}. The reply "
                   "is {{\"answer\", \"text\"}}.", u=req.base, k=c["token"]), 11, muted=True,
              wrap=580).pack(anchor="w", pady=(8, 0))
    app.button(f, t("Copy example (PowerShell)"), lambda: (w.clipboard_clear(), w.clipboard_append(
        f'Invoke-RestMethod -Method Post -Uri {req.base}/ask -Headers @{{Authorization="Bearer {c["token"]}"}} '
        '-ContentType "application/json" -Body \'{"title":"Build finished","message":"Deploy now?",'
        '"options":["Yes","No"]}\'')), primary=False).pack(anchor="w", pady=4)
    # chat shortcut
    r = ctk.CTkFrame(f, fg_color="transparent")
    r.pack(fill="x", pady=(10, 4))
    app.label(r, t("Quick chat shortcut"), 13).pack(side="left")
    hk = ctk.CTkEntry(r, width=160, height=30)
    hk.insert(0, c.get("chat_key", "Ctrl+Shift+Space"))
    hk.pack(side="right")
    hk.bind("<Return>", lambda e: (c.__setitem__("chat_key", hk.get().strip() or "Ctrl+Shift+Space"), app.save(),
                                   _start_key(app, chatwin)))

def _start_key(app, chatwin):
    from ui.overlay import Hotkey
    old = app.__dict__.get("_assist_key")
    if old:
        old.stop()
    app._assist_key = Hotkey(app, app.cfg["assistant"].get("chat_key", "Ctrl+Shift+Space"), chatwin.toggle)
    app._assist_key.start()

# ---------- the dashboard widget ----------
def build(app, body):
    st = app.__dict__.get("assistant")
    if not st:  # once per app run: the local address, the chat window and its shortcut
        req = Requests(app)
        req.start()
        st = app.assistant = {"req": req, "chat": ChatWindow(app)}
        _start_key(app, st["chat"])
    req, chatwin = st["req"], st["chat"]
    status = app.label(body, "", 12, muted=True, wrap=400)
    status.pack(anchor="w")
    def refresh():
        if not status.winfo_exists():
            return
        if req.error:
            return status.configure(text=t("Request pop-ups are off: port {p} is in use.", p=req.cfg.get("port", PORT)),
                                    text_color=WARN)
        on = claude_connected(req)
        keys = [PROVIDERS[p][0].split(" ")[0] for p in PROVIDERS if req.cfg.get("keys", {}).get(p)]
        status.configure(text=(t("Claude Code: connected") if on else t("Claude Code: not connected")) + "  ·  " +
                         (t("API keys: {k}", k=", ".join(keys)) if keys else t("No API key")),
                         text_color=ACCENT if on else MUTED)
    r = ctk.CTkFrame(body, fg_color="transparent")
    r.pack(fill="x", pady=(8, 0))
    app.button(r, t("Quick chat"), chatwin.toggle).pack(side="left")
    app.button(r, t("Prompt"), lambda: prompt_window(app, chatwin), primary=False, width=70).pack(side="left", padx=4)
    app.button(r, t("Pack project"), lambda: pack_window(app), primary=False, width=100).pack(side="left")
    r = ctk.CTkFrame(body, fg_color="transparent")
    r.pack(fill="x", pady=(6, 0))
    app.button(r, t("Settings"), lambda: settings_window(app, req, chatwin, refresh), primary=False,
               width=80).pack(side="left")
    refresh()
    app.every(5000, refresh, status, "Dashboard")
