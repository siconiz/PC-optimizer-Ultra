"""Downloadable AI optimization page (Ollama, LM Studio...): RAM / VRAM for local AI apps.
Loaded by core/addons.py only after the user downloads it; it provides page(app, p)."""
import json, re, urllib.request
import psutil
from core import boost, gpuinfo, memory as mem, procs
from core.i18n import t
from core.reg import HKCU, delete, get, set_value
from ui.theme import ACCENT, WARN

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

def page(app, p):
    c = app.cfg
    body = app.card(p, t("AI optimization"), t("Local AI (Ollama, LM Studio and similar) runs best with as much free "
                    "RAM and VRAM as possible. Right-click an AI app on the Boost page and choose 'Add as AI app': "
                    "when it starts, RAM is freed from background apps and it gets a higher priority."))
    r = app.row(body)
    out = app.label(r, "", 12, muted=True)
    def free():
        out.configure(text=t("Working..."), text_color=ACCENT)
        app.bg(procs.free_ram, lambda mb: out.configure(text=t("Freed {mb} MB of RAM.", mb=mb)),
               lambda m: out.configure(text=m, text_color=WARN))
    app.button(r, t("Free up RAM now"), free).pack(side="left")
    out.pack(side="left", padx=10)
    ai_apps = [x["name"] for x in c.get("boost", []) if x.get("ai")]
    app.label(body, t("AI apps: {names}", names=", ".join(ai_apps)) if ai_apps else t("No AI app added yet."),
              13).pack(anchor="w", pady=(8, 0))

    body = app.card(p, t("Memory for AI"))
    info = app.label(body, t("Checking..."), 13, wrap=820)
    info.pack(anchor="w")
    def show(_=None):
        s = mem.stats()
        gs = [g for g in gpuinfo.snapshot() if g["vendor"] != "Other"]
        lines = [t("RAM available: {a} GB of {total} GB", a=s["available"], total=s["total"])]
        lines += [t("{name}: {vram} GB VRAM", name=g["name"], vram=g["vram_gb"]) for g in gs]
        lines.append(t("A model needs roughly its file size in VRAM (plus some for context) to run fully on the GPU; "
                       "anything that does not fit runs on the CPU from RAM and is much slower."))
        info.configure(text="\n".join(lines))
    show()

    body = app.card(p, t("Ollama"), t("These settings cut Ollama's memory use with little quality loss (from the Ollama "
                    "FAQ): Flash Attention on, 8-bit KV cache, one request and one model at a time. Restart Ollama "
                    "after changing."))
    def set_env(v):
        boost.set_ollama_env(v)
        c["ollama_env"] = v
        app.save()
    app.switch_row(body, t("Ollama memory-saving settings"), "", bool(c.get("ollama_env")), set_env)
    adv = app.details(body)
    app.label(adv, t("Keep models in memory after use (OLLAMA_KEEP_ALIVE):"), 13).pack(anchor="w")
    opts = {t("1 minute"): "1m", t("5 minutes (default)"): None, t("30 minutes"): "30m"}
    ka = app.seg(app.row(adv, 4), list(opts), lambda v: set_keep_alive(opts[v]))
    ka.set(next((k for k, v in opts.items() if v == keep_alive()), t("5 minutes (default)")))
    ka.pack(side="left")
    app.label(adv, t("Shorter frees VRAM sooner for games; longer avoids reloading the model."), 12,
              muted=True).pack(anchor="w")
    _loaded(app, p)
    _vram_users(app, p)
    _fit(app, p)

def _loaded(app, p):
    body = app.card(p, t("Models loaded in Ollama"))
    tree = app.table(body, [("name", t("Model")), ("gb", t("Size (GB)")), ("vram", t("In VRAM (GB)"))], (320, 110, 120), 3)
    msg = app.label(body, "", 12, muted=True)
    msg.pack(anchor="w")
    def fill(ms):
        tree.delete(*tree.get_children())
        for m in ms:
            tree.insert("", "end", iid=m["name"], values=(m["name"], m["gb"], m["vram_gb"]))
        msg.configure(text="" if ms else t("No model loaded."))
    def refresh():
        app.bg(ollama_models, fill, lambda m: msg.configure(text=t("Ollama is not running.")))
    def unload():
        for name in tree.selection():
            app.bg(lambda n=name: ollama_unload(n), lambda _: refresh(), lambda m: msg.configure(text=m))
    r = app.row(body, (6, 0))
    app.button(r, t("Refresh"), refresh, primary=False).pack(side="left")
    app.button(r, t("Unload selected"), unload, primary=False).pack(side="left", padx=6)
    refresh()

def _vram_users(app, p):
    body = app.card(p, t("Apps using graphics memory"), t("Close apps you do not need before loading a big model "
                    "(browsers and launchers often hold VRAM)."))
    tree = app.table(body, [("name", t("App")), ("pid", "PID"), ("mb", t("VRAM (MB)"))], (320, 90, 120), 6)
    def fill(rows):
        tree.delete(*tree.get_children())
        for name, pid, mb in rows:
            tree.insert("", "end", iid=str(pid), values=(name, pid, mb))
    def refresh():
        app.bg(vram_by_process, fill, lambda m: None)
    def end():
        import psutil
        for iid in tree.selection():
            try:
                pr = psutil.Process(int(iid))
                if pr.name().lower() not in mem.PROTECTED:
                    pr.terminate()
            except (psutil.Error, OSError):
                pass
        app.after(800, refresh)
    r = app.row(body, (6, 0))
    app.button(r, t("Refresh"), refresh, primary=False).pack(side="left")
    app.button(r, t("End selected"), end, primary=False).pack(side="left", padx=6)
    refresh()

def _fit(app, p):
    import customtkinter as ctk
    body = app.card(p, t("Will this model fit?"), t("Rough estimate: weights + context (KV cache) + about 10% overhead."))
    r = app.row(body)
    size = ctk.CTkEntry(r, width=90, height=32, placeholder_text="8")
    size.pack(side="left")
    app.label(r, t("billion parameters"), 13).pack(side="left", padx=(6, 12))
    quants = {"Q4": 4.5, "Q5": 5.5, "Q8": 8.5, "FP16": 16}
    q = app.seg(r, list(quants))
    q.set("Q4")
    q.pack(side="left")
    ctxs = {"4K": 4, "8K": 8, "16K": 16, "32K": 32}
    c = app.seg(r, list(ctxs))
    c.set("8K")
    c.pack(side="left", padx=8)
    out = app.label(body, "", 13, wrap=820)
    out.pack(anchor="w", pady=(8, 0))
    def calc(*_):
        try:
            b = float(size.get() or 8)
        except ValueError:
            return
        need = estimate(b, quants[q.get()], ctxs[c.get()])
        vram = max((g["vram_gb"] for g in gpuinfo.snapshot() if g["vendor"] != "Other"), default=0)
        ram = mem.stats()["available"] or 0
        if need <= vram * 0.95:
            msg, color = t("About {n} GB: fits in VRAM ({v} GB). Runs fully on the GPU.", n=need, v=vram), ACCENT
        elif need <= vram + ram:
            msg, color = t("About {n} GB: more than VRAM ({v} GB). Part runs on the CPU, which is much slower. Try a "
                           "smaller quantization or context.", n=need, v=vram), WARN
        else:
            msg, color = t("About {n} GB: does not fit in VRAM + free RAM ({x} GB).", n=need, x=round(vram + ram, 1)), WARN
        out.configure(text=msg, text_color=color)
    for w in (q, c):
        w.configure(command=calc)
    size.bind("<KeyRelease>", calc)
    calc()
