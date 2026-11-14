"""Downloadable AI optimization page (Ollama, LM Studio...): RAM / VRAM for local AI apps.
Loaded by core/addons.py only after the user downloads it; it provides page(app, p)."""
import ctypes, json, os, re, shutil, subprocess, urllib.request
import psutil
from core import boost, gpuinfo, memory as mem, procs
from core.i18n import t
from core.reg import HKCU, delete, get, set_value
from ui.theme import ACCENT, BG, CARD, CARD2, F, HOVER2, MUTED, WARN

OLLAMA = "http://127.0.0.1:11434"
ENV = "Environment"
AI_EXES = {"ollama.exe", "ollama app.exe", "lm studio.exe", "lms.exe", "koboldcpp.exe", "llama-server.exe",
           "jan.exe", "gpt4all.exe", "comfyui.exe"}

def _api(path, body=None, timeout=5):
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")

def ollama_unload(name):
    _api("/api/generate", {"model": name, "keep_alive": 0})  # Ollama FAQ: keep_alive 0 unloads at once

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

# ---------- Ollama: models, per-model settings, speed ----------
NO_WINDOW = 0x08000000
SUFFIX = "-pco"  # per-model settings live in a copy named '<model>:<tag>-pco' (same weights, no extra disk)

def installed():
    """Downloaded models without our copies: [{'name', 'gb'}]."""
    return sorted(({"name": m["name"], "gb": round(m["size"] / 2**30, 1)} for m in _api("/api/tags").get("models", [])
                   if not m["name"].endswith(SUFFIX)), key=lambda m: m["name"])

def running():
    """{name: {'gb', 'vram_gb', 'gpu_pct', 'ctx'}} for models in memory now."""
    out = {}
    for m in _api("/api/ps").get("models", []):
        size, vram = m.get("size") or 1, m.get("size_vram") or 0
        out[m["name"]] = {"gb": round(size / 2**30, 1), "vram_gb": round(vram / 2**30, 1),
                          "gpu_pct": round(100 * vram / size), "ctx": m.get("context_length")}
    return out

def variant(name):
    base, _, tag = name.partition(":")
    return f"{base}:{tag or 'latest'}{SUFFIX}"

def params_of(s):
    """Model parameters (Ollama Modelfile names) from the settings a user picked; empty = model defaults."""
    p = {"num_ctx": s.get("ctx"), "num_thread": s.get("threads"), "temperature": s.get("temp"),
         "num_predict": s.get("max_tokens"), "main_gpu": s.get("main_gpu")}
    if s.get("place") == "cpu":
        p["num_gpu"] = 0  # no layers on the GPU
    if s.get("keep_ram"):
        p["use_mmap"] = False  # read the whole model into RAM instead of paging it in from disk
    return {k: v for k, v in p.items() if v not in (None, "")}

def prepare(name, s):
    """Model name to load: the original, or a copy holding the chosen settings (re-made when they change).
    A copy is needed because Ollama reloads a model with its own defaults when a chat app asks for it."""
    params = params_of(s)
    if not params:
        return name
    v = variant(name)
    if s.get("_made") != json.dumps(params, sort_keys=True):
        _api("/api/create", {"model": v, "from": name, "parameters": params, "stream": False}, 300)
        s["_made"] = json.dumps(params, sort_keys=True)
    return v

def load(name, keep):
    """Loads a model into memory and keeps it there (keep: '-1' forever, '10m', ...)."""
    _api("/api/generate", {"model": name, "keep_alive": -1 if keep in (None, "-1") else keep}, 900)

def bench(name, threads=None):
    """Tokens per second for one short answer (eval_count / eval_duration in ns, from the Ollama API docs)."""
    opts = {"num_predict": 96, "temperature": 0, "seed": 1}
    if threads:
        opts["num_thread"] = threads
    r = _api("/api/generate", {"model": name, "stream": False, "options": opts,
                               "prompt": "Explain in a few sentences how a CPU cache works."}, 900)
    return round(r["eval_count"] / max(1, r["eval_duration"]) * 1e9, 1), round(r.get("load_duration", 0) / 1e9, 1)

def tune_threads(name):
    """llama.cpp tip: start at 1 thread and double while it gets faster. Returns (best, {threads: tok/s})."""
    phys = psutil.cpu_count(logical=False) or 4
    tries, res = sorted({n for n in (1, 2, 4, 8, 12, 16, 24, 32) if n <= phys} | {phys}), {}
    for n in tries:
        res[n] = bench(name, n)[0]
        if len(res) > 2 and res[n] < max(res.values()) * 0.9:
            break  # clearly slower than the best so far: more threads will not help
    return max(res, key=res.get), res

# ---------- Ollama: server settings (user environment variables) ----------
SETTINGS = {  # name: (choices shown, values; None = Ollama default). Names checked in Ollama's envconfig/config.go
    "OLLAMA_KV_CACHE_TYPE": (["f16", "q8_0", "q4_0"], [None, "q8_0", "q4_0"]),
    "OLLAMA_FLASH_ATTENTION": (["Auto", "On"], [None, "1"]),
    "OLLAMA_CONTEXT_LENGTH": (["Auto", "4K", "8K", "16K", "32K"], [None, "4096", "8192", "16384", "32768"]),
    "OLLAMA_NUM_PARALLEL": (["1", "2", "4"], [None, "2", "4"]),
    "OLLAMA_MAX_LOADED_MODELS": (["Auto", "1", "2", "3"], [None, "1", "2", "3"]),
    "OLLAMA_GPU_OVERHEAD": (["0", "512 MB", "1 GB", "2 GB"], [None, str(512 * 2**20), str(2**30), str(2 * 2**30)]),
}
RECOMMENDED = {"OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_NUM_PARALLEL": None,
               "OLLAMA_MAX_LOADED_MODELS": "1"}

def env(k):
    return get(HKCU, ENV, k)

def set_env(k, v):
    delete(HKCU, ENV, k) if v is None else set_value(HKCU, ENV, k, v)
    # WM_SETTINGCHANGE "Environment": apps started from Explorer from now on see the new value
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, "Environment", 2, 3000, None)

def restart_ollama():
    """Stops Ollama and starts its tray app again with the current user environment."""
    for pr in psutil.process_iter(["name"]):
        if (pr.info["name"] or "").lower() in ("ollama app.exe", "ollama.exe"):
            try:
                pr.kill()
            except psutil.Error:
                pass
    e = dict(os.environ)
    for k in list(SETTINGS) + ["OLLAMA_SCHED_SPREAD", "CUDA_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES",
                               "OLLAMA_MODELS", "OLLAMA_KEEP_ALIVE"]:
        v = env(k)
        e.pop(k, None) if v is None else e.__setitem__(k, v)
    tray = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama app.exe")
    cmd = [tray] if os.path.exists(tray) else [shutil.which("ollama") or "ollama", "serve"]
    subprocess.Popen(cmd, env=e, creationflags=NO_WINDOW, close_fds=True)

def gpus():
    """[(label, id)] of graphics cards Ollama can use; NVIDIA ids are UUIDs (Ollama docs: more stable than numbers)."""
    out = []
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10, creationflags=NO_WINDOW)
        out = [(f"GPU {m[0]}: {m[1]}", m[2]) for m in re.findall(r"GPU (\d+): (.+?) \(UUID: (GPU-[\w-]+)\)", r.stdout)]
    except (OSError, subprocess.SubprocessError):
        pass
    amd = [g for g in gpuinfo.snapshot() if g["vendor"] == "AMD"]
    return out + [(f"AMD {i}: {g['name']}", str(i)) for i, g in enumerate(amd)]

def models_dir():
    return env("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")

def move_models(dest):
    """Moves the model folder (often tens of GB) to dest and points OLLAMA_MODELS there."""
    src, new = models_dir(), os.path.join(dest, "OllamaModels")
    for pr in psutil.process_iter(["name"]):
        if (pr.info["name"] or "").lower() in ("ollama app.exe", "ollama.exe"):
            try:
                pr.kill()
            except psutil.Error:
                pass
    shutil.move(src, new)
    set_env("OLLAMA_MODELS", new)
    restart_ollama()
    return new

# ---------- RAM and page file ----------
class _MemStatus(ctypes.Structure):
    _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [(n, ctypes.c_ulonglong) for n in (
        "total", "avail", "commit_limit", "commit_avail", "virt_total", "virt_avail", "ext")]

def commit():
    """(commit limit GB, free GB): RAM + page file, what all programs together may use."""
    m = _MemStatus()
    m.len = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return round(m.commit_limit / 2**30, 1), round(m.commit_avail / 2**30, 1)

def pagefile():
    """{'auto': Windows manages the size, 'files': [(path, MB)]}"""
    import wmi
    c = wmi.WMI()
    return {"auto": bool(c.Win32_ComputerSystem()[0].AutomaticManagedPagefile),
            "files": [(f.Name, int(f.AllocatedBaseSize or 0)) for f in c.Win32_PageFileUsage()]}

def set_auto_pagefile():
    """Lets Windows grow the page file when memory runs short (up to 3x RAM, Microsoft Learn). Restart to apply."""
    subprocess.run(["powershell", "-NoProfile", "-Command", "$c = Get-CimInstance Win32_ComputerSystem; "
                    "Set-CimInstance -InputObject $c -Property @{AutomaticManagedPagefile=$true}"],
                   check=True, capture_output=True, creationflags=NO_WINDOW, timeout=60)

def headroom(model_gb, ctx_gb=1.0):
    """Where a model of this size would go: (fits_vram, fits_ram, fits_commit, free VRAM GB, free RAM GB)."""
    gs = [g for g in gpuinfo.snapshot() if g["vendor"] != "Other"]
    vram = sum(max(0, g["vram_gb"] - g.get("vram_used_gb", 0)) for g in gs)
    ram = mem.stats()["available"] or 0
    need = model_gb * 1.1 + ctx_gb
    return need <= vram, need <= vram + ram, need <= vram + commit()[1], round(vram, 1), round(ram, 1)

# ---------- AI mode ----------
def ai_mode(app):
    """One click before using a local AI: free RAM, Ollama/LM Studio get priority (performance cores) and are never
    slowed down, power mode to best performance. Returns what was done."""
    from core import cooling
    c, done = app.cfg, []
    mb = procs.free_ram(keep=sorted(AI_EXES))
    done.append(t("Freed {mb} MB of RAM", mb=mb))
    names = {x["exe"] for x in c.setdefault("boost", [])}
    for exe in ("ollama.exe", "lm studio.exe", "llama-server.exe"):
        if exe not in names:
            prof = boost.new_profile(exe[:-4].title(), exe, ai=True)
            prof.update(priority="High", cores="auto")
            c["boost"].append(prof)
    from core.auto import DEFAULT_EXCEPTIONS
    ex = c.setdefault("exceptions", list(DEFAULT_EXCEPTIONS))
    ex += [e for e in ("ollama.exe", "ollama app.exe", "lm studio.exe") if e not in ex]
    done.append(t("Ollama and LM Studio: high priority, performance cores, never slowed down"))
    cooling.set_power_mode("Best performance")
    done.append(t("Power mode: {mode}", mode=t("Best performance")))
    return done

def page(app, p):
    a = app.cfg.setdefault("ai", {})
    body = app.card(p, t("AI optimization"), t("Local AI (Ollama, LM Studio and similar) runs best with as much free "
                    "RAM and VRAM as possible. AI mode does everything below that helps, in one click."))
    r = app.row(body)
    out = app.label(body, "", 12, muted=True, wrap=860)
    def mode():
        out.configure(text=t("Working..."), text_color=ACCENT)
        app.bg(lambda: ai_mode(app), lambda done: (app.save(), out.configure(text="  ·  ".join(done))),
               lambda m: out.configure(text=m, text_color=WARN))
    def free():
        app.bg(lambda: procs.free_ram(keep=sorted(AI_EXES)),
               lambda mb: out.configure(text=t("Freed {mb} MB of RAM.", mb=mb), text_color=ACCENT), lambda m: None)
    app.button(r, t("AI mode"), mode).pack(side="left")
    app.button(r, t("Free up RAM now"), free, primary=False).pack(side="left", padx=6)
    app.tip(r, t("AI mode: frees RAM, gives Ollama and LM Studio high priority on the performance cores, keeps "
                 "them out of background slow-down and sets the best performance power mode."))
    out.pack(anchor="w", pady=(6, 0))
    _switcher_card(app, p)
    _memory(app, p)
    _settings(app, p)
    _loaded(app, p)
    _speed(app, p)
    _vram_users(app, p)
    _fit(app, p)

def _memory(app, p):
    body = app.card(p, t("Memory for AI"), t("A model runs fastest fully in VRAM. What does not fit runs on the CPU "
                    "from RAM (slower); what does not fit in RAM goes to the page file on the SSD (much slower, "
                    "but it does not crash)."))
    info = app.label(body, t("Checking..."), 13, wrap=860)
    info.pack(anchor="w")
    r = app.row(body, (6, 0))
    def show(pf):
        s = mem.stats()
        lim, free = commit()
        lines = [f"{g['name']}: {g['vram_gb']} GB VRAM ({t('{u} GB in use', u=g.get('vram_used_gb', 0))})"
                 for g in gpuinfo.snapshot() if g["vendor"] != "Other"]
        lines += [t("RAM available: {a} GB of {total} GB", a=s["available"], total=s["total"]),
                  t("RAM + page file: {f} GB free of {l} GB", f=free, l=lim),
                  t("Page file: {how}", how=t("managed by Windows (grows when needed)") if pf["auto"] else
                    t("fixed size") + " - " + ", ".join(f"{n} {mb // 1024} GB" for n, mb in pf["files"]))]
        info.configure(text="\n".join(lines))
        if not pf["auto"] and not r.winfo_children():
            def auto():
                if app.ask(t("Page file"), t("Let Windows grow the page file when memory runs short (up to 3x RAM, "
                           "limited by free disk space)? It applies after a restart.")):
                    app.bg(set_auto_pagefile, lambda _: info.configure(text=info.cget("text") + "\n" +
                           t("Done. Restart the PC to apply.")), lambda m: info.configure(text=m, text_color=WARN))
            app.button(r, t("Let Windows manage the page file"), auto, primary=False).pack(side="left")
    app.bg(pagefile, show, lambda m: info.configure(text=m))

def _settings(app, p):
    import customtkinter as ctk
    body = app.card(p, t("Ollama settings"), t("Saved for your Windows user (environment variables). Restart Ollama "
                    "to apply."))
    labels = {"OLLAMA_KV_CACHE_TYPE": t("Context memory (KV cache): q8_0 uses half the memory of f16"),
              "OLLAMA_FLASH_ATTENTION": t("Flash Attention (needed for the KV cache setting)"),
              "OLLAMA_CONTEXT_LENGTH": t("Default context length"),
              "OLLAMA_NUM_PARALLEL": t("Requests at the same time (each one adds context memory)"),
              "OLLAMA_MAX_LOADED_MODELS": t("Models in memory at once"),
              "OLLAMA_GPU_OVERHEAD": t("VRAM kept free for other apps (per GPU)")}
    segs = {}
    for k, (names, vals) in SETTINGS.items():
        r = app.row(body, 3)
        app.label(r, labels[k], 13).pack(side="left")
        shown = [t(n) for n in names]
        seg = app.seg(r, shown, lambda v, k=k, shown=shown, vals=vals: set_env(k, vals[shown.index(v)]))
        cur = env(k)
        seg.set(shown[vals.index(cur)] if cur in vals else shown[0])
        seg.pack(side="right")
        segs[k] = (seg, shown, vals)
    msg = app.label(body, "", 12, muted=True, wrap=860)
    r = app.row(body, (8, 0))
    def recommended():
        for k, v in RECOMMENDED.items():
            set_env(k, v)
            seg, shown, vals = segs[k]
            seg.set(shown[vals.index(v)])
        msg.configure(text=t("Recommended settings saved. Restart Ollama to apply."), text_color=ACCENT)
    def restart():
        app.bg(restart_ollama, lambda _: msg.configure(text=t("Ollama restarted."), text_color=ACCENT),
               lambda m: msg.configure(text=m, text_color=WARN))
    app.button(r, t("Recommended for 8-12 GB GPUs"), recommended, primary=False).pack(side="left")
    app.button(r, t("Restart Ollama"), restart).pack(side="left", padx=6)
    msg.pack(anchor="w", pady=(4, 0))

    # several graphics cards
    gbox = ctk.CTkFrame(body, fg_color="transparent")
    gbox.pack(fill="x", pady=(10, 0))
    def show_gpus(gs):
        app.label(gbox, t("Graphics cards for AI"), 13, bold=True).pack(anchor="w")
        if len(gs) < 2:
            app.label(gbox, t("One graphics card found: Ollama uses it automatically."), 12, muted=True).pack(anchor="w")
            return
        key = "CUDA_VISIBLE_DEVICES" if gs[0][1].startswith("GPU-") else "ROCR_VISIBLE_DEVICES"
        on = set((env(key) or "").split(",")) - {""}
        vars_ = []
        def save():
            ids = [i for (_, i), v in zip(gs, vars_) if v.get()]
            set_env(key, None if len(ids) == len(gs) or not ids else ",".join(ids))
        for label, i in gs:
            v = ctk.BooleanVar(value=not on or i in on)
            vars_.append(v)
            ctk.CTkCheckBox(gbox, text=label, variable=v, command=save, font=F(12), fg_color=ACCENT,
                            hover_color=ACCENT).pack(anchor="w", pady=2)
        app.switch_row(gbox, t("Spread every model over all graphics cards"), t("Off (Ollama default): a model that "
                       "fits on one card stays on it, which is usually faster; bigger models are spread anyway."),
                       env("OLLAMA_SCHED_SPREAD") == "1", lambda o: set_env("OLLAMA_SCHED_SPREAD", "1" if o else None))
    app.bg(gpus, show_gpus, lambda m: None)

    # where the models are stored
    r = app.row(body, (10, 0))
    where = app.label(r, t("Models are stored in: {d}", d=models_dir()), 12, muted=True)
    where.pack(side="left")
    def move():
        from tkinter import filedialog
        dest = filedialog.askdirectory(title=t("Move the Ollama models to"))
        if dest and app.ask(t("Move models"), t("Move all Ollama models to {d}? Ollama stops while they move; this "
                            "can take a while for big models.", d=dest)):
            where.configure(text=t("Moving..."))
            app.bg(lambda: move_models(dest.replace("/", "\\")), lambda d: where.configure(
                text=t("Models are stored in: {d}", d=d)), lambda m: where.configure(text=m, text_color=WARN))
    app.button(r, t("Move to another drive..."), move, primary=False).pack(side="right")

def _gpu_text(m):
    return t("100% GPU") if m["gpu_pct"] >= 100 else t("{g}% GPU / {c}% CPU", g=m["gpu_pct"], c=100 - m["gpu_pct"])

def _loaded(app, p):
    body = app.card(p, t("Models loaded in Ollama"), t("Anything on the CPU is much slower: use a smaller "
                    "quantization or a shorter context, or close apps that hold VRAM."))
    tree = app.table(body, [("name", t("Model")), ("gb", t("Size (GB)")), ("vram", t("In VRAM (GB)")),
                            ("where", t("Runs on")), ("ctx", t("Context"))], (280, 90, 110, 170, 90), 3)
    msg = app.label(body, "", 12, muted=True)
    msg.pack(anchor="w")
    def fill(ms):
        tree.delete(*tree.get_children())
        for name, m in ms.items():
            tree.insert("", "end", iid=name, values=(name, m["gb"], m["vram_gb"], _gpu_text(m), m["ctx"] or "-"))
        msg.configure(text="" if ms else t("No model loaded."))
    def refresh():
        app.bg(running, fill, lambda m: msg.configure(text=t("Ollama is not running.")))
    def unload():
        for name in tree.selection():
            app.bg(lambda n=name: ollama_unload(n), lambda _: refresh(), lambda m: msg.configure(text=m))
    r = app.row(body, (6, 0))
    app.button(r, t("Refresh"), refresh, primary=False).pack(side="left")
    app.button(r, t("Unload selected"), unload, primary=False).pack(side="left", padx=6)
    refresh()
    app.every(5000, refresh, tree, "AI optimization")

def _speed(app, p):
    import customtkinter as ctk
    a = app.cfg["ai"]
    body = app.card(p, t("Speed test"), t("Loads a model and times a short answer (tokens per second). Close games "
                    "first: the test uses the GPU fully."))
    r = app.row(body)
    pick = ctk.CTkOptionMenu(r, values=["-"], width=280, height=32, fg_color=CARD2, button_color=CARD2,
                             button_hover_color=HOVER2)
    pick.pack(side="left")
    tree = app.table(body, [("name", t("Model")), ("tps", t("Tokens/s")), ("where", t("Runs on")),
                            ("load", t("Load (s)"))], (300, 100, 180, 90), 4)
    msg = app.label(body, "", 12, muted=True)
    def fill():
        tree.delete(*tree.get_children())
        for name, (tps, where, load_s) in sorted(a.get("bench", {}).items(), key=lambda x: -x[1][0]):
            tree.insert("", "end", values=(name, tps, where, load_s))
    def run():
        name = pick.get()
        if name == "-":
            return
        msg.configure(text=t("Measuring {name}...", name=name), text_color=MUTED)
        def work():
            tps, load_s = bench(name)
            m = running().get(name)
            return tps, _gpu_text(m) if m else "-", load_s
        def done(res):
            a.setdefault("bench", {})[name] = list(res)
            app.save()
            fill()
            msg.configure(text=t("{name}: {tps} tokens/s", name=name, tps=res[0]), text_color=ACCENT)
        app.bg(work, done, lambda m: msg.configure(text=m, text_color=WARN))
    app.button(r, t("Measure"), run).pack(side="left", padx=6)
    msg.pack(anchor="w", pady=(4, 0))
    app.bg(installed, lambda ms: (pick.configure(values=[m["name"] for m in ms] or ["-"]),
                                  pick.set(ms[0]["name"] if ms else "-")), lambda m: None)
    fill()

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
        vram = sum(g["vram_gb"] for g in gpuinfo.snapshot() if g["vendor"] != "Other")  # all cards together
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

# ---------- model switcher: a small window to turn models on and off ----------
def _ctx_gb(s):
    return (s.get("ctx") or 4096) / 8192  # rough: about 1 GB of context memory per 8K tokens (8B-class, f16)

class ModelBar:
    """Always-on-top window with one switch per downloaded model, presets and per-model settings. Turning a model
    on frees RAM, makes room in VRAM if needed, loads the model with its settings and shows where it runs."""
    def __init__(self, app):
        self.app, self.a, self.win, self.rows, self.sizes = app, app.cfg["ai"], None, {}, {}
        self.busy = set()

    def toggle(self):
        self.hide() if self.win else self.show()

    def show(self):
        import customtkinter as ctk
        if self.win:
            return self.win.lift()
        w = self.win = ctk.CTkToplevel(self.app, fg_color=BG)
        w.title(t("AI models"))
        w.geometry(self.a.get("bar_geo") or f"340x440+{w.winfo_screenwidth() - 380}+80")  # top right
        w.attributes("-topmost", True)
        w.attributes("-alpha", self.a.get("bar_alpha", 0.96))
        w.protocol("WM_DELETE_WINDOW", self.hide)
        top = ctk.CTkFrame(w, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))
        self.preset = ctk.CTkOptionMenu(top, values=[t("Preset")] + list(self.a.get("presets", {})), width=170,
                                        height=30, fg_color=CARD2, button_color=CARD2, button_hover_color=HOVER2,
                                        command=self.use_preset)
        self.preset.pack(side="left")
        self.app.button(top, t("Save"), self.save_preset, primary=False, width=70).pack(side="left", padx=6)
        self.list = ctk.CTkScrollableFrame(w, fg_color="transparent")
        self.list.pack(fill="both", expand=True, padx=4)
        self.status = self.app.label(w, "", 11, muted=True, wrap=310)
        self.status.pack(anchor="w", padx=10, pady=(2, 8))
        self.rows = {}
        self.refresh()
        self.app.every(4000, self.refresh, self.status, None)

    def hide(self):
        if self.win:
            self.a["bar_geo"] = self.win.geometry()
            self.app.save()
            self.win.destroy()
            self.win = None

    def refresh(self):
        self.app.bg(lambda: (installed(), running()), self.fill, lambda m: self.say(t("Ollama is not running.")))

    def say(self, text, color=None):
        if self.win:
            self.status.configure(text=text, text_color=color or MUTED)

    def fill(self, data):
        import customtkinter as ctk
        if not self.win:
            return
        models, run = data
        self.sizes = {m["name"]: m["gb"] for m in models}
        for m in models:
            name = m["name"]
            state = run.get(name) or run.get(variant(name))
            if name not in self.rows:
                f = ctk.CTkFrame(self.list, fg_color=CARD, corner_radius=10)
                f.pack(fill="x", pady=3, padx=2)
                lbl = self.app.label(f, name, 13, bold=True)
                lbl.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 0))
                sub = self.app.label(f, "", 11, muted=True)
                sub.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))
                sw = ctk.CTkSwitch(f, text="", width=46, progress_color=ACCENT, command=lambda n=name: self.flip(n))
                sw.grid(row=0, column=1, rowspan=2, padx=(4, 0))
                gear = ctk.CTkButton(f, text="⚙", width=30, height=28, fg_color=CARD2, hover_color=HOVER2,
                                     command=lambda n=name: ModelSettings(self, n))
                gear.grid(row=0, column=2, rowspan=2, padx=(0, 8))
                f.grid_columnconfigure(0, weight=1)
                self.rows[name] = (sub, sw)
            sub, sw = self.rows[name]
            where = t("Loading...") if name in self.busy else _gpu_text(state) if state else t("Off")
            sub.configure(text=f"{m['gb']} GB  ·  {where}")
            if name not in self.busy:
                sw.select() if state else sw.deselect()

    def flip(self, name):
        sub, sw = self.rows[name]
        self.switch_on(name) if sw.get() else self.switch_off(name)

    def switch_off(self, name):
        self.app.bg(lambda: [ollama_unload(n) for n in (name, variant(name)) if n in running()],
                    lambda _: (self.say(t("{name} unloaded.", name=name)), self.refresh()), lambda m: self.say(m, WARN))

    def switch_on(self, name, then=None):
        s = self.a.setdefault("models", {}).setdefault(name, {})
        self.busy.add(name)
        self.say(t("Loading {name}...", name=name))
        def work():
            notes = []
            if self.a.get("free_ram", True):
                procs.free_ram(keep=sorted(AI_EXES))
            fits_vram, fits_ram, fits_commit, vfree, rfree = headroom(self.sizes.get(name, 0), _ctx_gb(s))
            loaded = running()
            if not fits_vram and loaded and self.a.get("make_room", True):
                for n in loaded:
                    ollama_unload(n)
                notes.append(t("Unloaded {names} to make room.", names=", ".join(loaded)))
                fits_vram, fits_ram, fits_commit, vfree, rfree = headroom(self.sizes.get(name, 0), _ctx_gb(s))
            if not fits_commit:
                notes.append(t("Not enough RAM + page file: loading may fail."))
            elif not fits_ram:
                notes.append(t("Part goes to the page file: it will be very slow."))
            target = prepare(name, s)
            load(target, self.a.get("keep", "-1"))
            m = running().get(target)
            return target, m, notes
        def done(res):
            target, m, notes = res
            self.busy.discard(name)
            self.app.save()
            text = t("{name}: {where}", name=target, where=_gpu_text(m) if m else t("loaded"))
            self.say("  ".join([text] + notes), WARN if notes or (m and m["gpu_pct"] < 100) else ACCENT)
            self.refresh()
            if then:
                then()
        def fail(msg):
            self.busy.discard(name)
            self.say(msg, WARN)
            self.refresh()
        self.app.bg(work, done, fail)

    def use_preset(self, preset):
        names = self.a.get("presets", {}).get(preset)
        if not names:
            return
        self.a["current_preset"] = preset
        def unload_others():
            keep = set(names) | {variant(n) for n in names}
            for n in running():
                if n not in keep:
                    ollama_unload(n)
        def chain(i=0):
            if i < len(names):
                self.switch_on(names[i], lambda: chain(i + 1))
        self.app.bg(unload_others, lambda _: chain(), lambda m: self.say(m, WARN))

    def save_preset(self):
        import customtkinter as ctk
        on = [n for n, (sub, sw) in self.rows.items() if sw.get()]
        if not on:
            return self.say(t("Turn on the models for this preset first."), WARN)
        name = ctk.CTkInputDialog(title=t("Save preset"), text=t("Name for these models: {names}",
                                                                   names=", ".join(on))).get_input()
        if name:
            self.a.setdefault("presets", {})[name.strip()] = on
            self.app.save()
            self.preset.configure(values=[t("Preset")] + list(self.a["presets"]))
            self.preset.set(name.strip())

class ModelSettings:
    """Settings of one model, saved in a copy of it ('<model>-pco') so every chat app gets them."""
    def __init__(self, bar, name):
        import customtkinter as ctk
        self.bar, self.name, app = bar, name, bar.app
        s = self.s = bar.a.setdefault("models", {}).setdefault(name, {})
        w = self.w = ctk.CTkToplevel(bar.win or app, fg_color=BG)
        w.title(name)
        w.attributes("-topmost", True)
        w.geometry("520x560")
        f = ctk.CTkScrollableFrame(w, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=12, pady=12)
        app.label(f, name, 15, bold=True).pack(anchor="w")
        app.label(f, t("Saved as {v}. Choose that name in your chat app to use these settings; the switcher loads it "
                       "for you.", v=variant(name)), 12, muted=True, wrap=460).pack(anchor="w", pady=(2, 10))
        places = {t("GPU first, CPU helps when VRAM is short"): None, t("CPU only (keeps VRAM free)"): "cpu"}
        self.place = self._seg(f, t("Where it runs"), places, s.get("place"))
        ctxs = {t("Auto"): None, "4K": 4096, "8K": 8192, "16K": 16384, "32K": 32768}
        self.ctx = self._seg(f, t("Context length"), ctxs, s.get("ctx"))
        r = app.row(f, 4)
        app.label(r, t("CPU threads"), 13).pack(side="left")
        self.threads = ctk.CTkEntry(r, width=70, height=30, placeholder_text=t("Auto"))
        self.threads.pack(side="right")
        if s.get("threads"):
            self.threads.insert(0, str(s["threads"]))
        self.tune_btn = app.button(r, t("Find fastest"), self.tune, primary=False, width=110)
        self.tune_btn.pack(side="right", padx=6)
        app.label(f, t("Only matters for the part that runs on the CPU. Find fastest tries 1, 2, 4 ... threads up to "
                       "the number of cores (takes a minute)."), 11, muted=True, wrap=460).pack(anchor="w")
        self.keep_ram = app.switch_row(f, t("Keep the whole model in RAM"), t("Reads the model into RAM when it loads "
                                       "instead of from disk as needed. Uses more RAM, avoids stalls."),
                                       bool(s.get("keep_ram")), lambda on: None)
        r = app.row(f, 4)
        app.label(r, t("Temperature (blank = model default)"), 13).pack(side="left")
        self.temp = ctk.CTkEntry(r, width=70, height=30, placeholder_text="0.8")
        self.temp.pack(side="right")
        r = app.row(f, 4)
        app.label(r, t("Longest answer in tokens (blank = no limit)"), 13).pack(side="left")
        self.maxt = ctk.CTkEntry(r, width=70, height=30, placeholder_text="-")
        self.maxt.pack(side="right")
        for e, k in ((self.temp, "temp"), (self.maxt, "max_tokens")):
            if s.get(k) is not None:
                e.insert(0, str(s[k]))
        self.msg = app.label(f, "", 12, muted=True, wrap=460)
        self.msg.pack(anchor="w", pady=(8, 0))
        r = app.row(f, (10, 0))
        app.button(r, t("Save"), self.save).pack(side="left")
        app.button(r, t("Reset to model defaults"), self.reset, primary=False).pack(side="left", padx=6)

    def _seg(self, parent, label, choices, current):
        app = self.bar.app
        r = app.row(parent, 4)
        app.label(r, label, 13).pack(side="left")
        seg = app.seg(r, list(choices))
        seg.set(next((k for k, v in choices.items() if v == current), list(choices)[0]))
        seg.pack(side="right")
        seg._choices = choices
        return seg

    @staticmethod
    def _num(entry, kind):
        try:
            return kind(entry.get()) if entry.get().strip() else None
        except ValueError:
            return None

    def save(self):
        s = self.s
        s.update(place=self.place._choices[self.place.get()], ctx=self.ctx._choices[self.ctx.get()],
                 threads=self._num(self.threads, int), temp=self._num(self.temp, float),
                 max_tokens=self._num(self.maxt, int), keep_ram=bool(self.keep_ram.get()))
        self.bar.app.save()
        self.msg.configure(text=t("Saved. Turn the model off and on to use the new settings."), text_color=ACCENT)

    def reset(self):
        self.s.clear()
        self.bar.app.save()
        self.w.destroy()

    def tune(self):
        self.save()
        self.tune_btn.configure(state="disabled")
        self.msg.configure(text=t("Measuring... this loads the model several times."), text_color=MUTED)
        def done(res):
            best, all_ = res
            self.tune_btn.configure(state="normal")
            self.threads.delete(0, "end")
            self.threads.insert(0, str(best))
            self.save()
            self.msg.configure(text=t("Fastest: {n} threads.", n=best) + "  " + ", ".join(
                f"{n}: {v}" for n, v in all_.items()) + " " + t("tokens/s"), text_color=ACCENT)
        def fail(m):
            self.tune_btn.configure(state="normal")
            self.msg.configure(text=m, text_color=WARN)
        self.bar.app.bg(lambda: tune_threads(prepare(self.name, self.s)), done, fail)

def _foreground_exe():
    import win32gui, win32process
    _, pid = win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())
    return psutil.Process(pid).name().lower()

def _switcher_card(app, p):
    """Model switcher settings; also starts what runs in the background: shortcut, startup model, game and
    app-in-front rules (the page is built once, shortly after the app starts)."""
    import customtkinter as ctk
    from ui.overlay import Hotkey
    a = app.cfg["ai"]
    bar = app.__dict__.setdefault("ai_bar", ModelBar(app))
    body = app.card(p, t("Model switcher"), t("A small window that stays on top: turn models on and off, switch "
                    "presets, and each model's settings. Turning a model on frees RAM and makes room in VRAM first."))
    r = app.row(body)
    app.button(r, t("Open model switcher"), bar.toggle).pack(side="left")
    hk = ctk.CTkEntry(r, width=150, height=32)
    hk.insert(0, a.get("hotkey", "Ctrl+Shift+M"))
    hk.pack(side="left", padx=8)
    def start_key(*_):
        a["hotkey"] = hk.get().strip() or "Ctrl+Shift+M"
        app.save()
        old = app.__dict__.get("_ai_key")
        if old:
            old.stop()
        app._ai_key = Hotkey(app, a["hotkey"], bar.toggle)
        app._ai_key.start()
    hk.bind("<Return>", start_key)
    app.tip(hk, t("Shortcut to open and close the switcher. Press Enter to apply."))
    keeps = {t("Never"): "-1", t("10 min"): "10m", t("30 min"): "30m", t("1 hour"): "60m"}
    r = app.row(body, 4)
    app.label(r, t("Unload a model when it is not used for"), 13).pack(side="left")
    seg = app.seg(r, list(keeps), lambda v: (a.__setitem__("keep", keeps[v]), app.save()))
    seg.set(next((k for k, v in keeps.items() if v == a.get("keep", "-1")), t("Never")))
    seg.pack(side="right")
    app.switch_row(body, t("Unload models while a game runs"), t("Gives the game all the VRAM; when the game "
                   "closes you are asked to load them again."), a.get("game_unload", True),
                   lambda on: (a.__setitem__("game_unload", on), app.save()))
    app.switch_row(body, t("Make room in VRAM automatically"), t("Unloads other models when the new one would not "
                   "fit in VRAM."), a.get("make_room", True), lambda on: (a.__setitem__("make_room", on), app.save()))
    r = app.row(body, 4)
    app.label(r, t("Load at startup"), 13).pack(side="left")
    start = ctk.CTkOptionMenu(r, values=[t("None")], width=220, height=30, fg_color=CARD2, button_color=CARD2,
                              button_hover_color=HOVER2,
                              command=lambda v: (a.__setitem__("startup", None if v == t("None") else v), app.save()))
    start.set(a.get("startup") or t("None"))
    start.pack(side="right")
    app.bg(installed, lambda ms: start.configure(values=[t("None")] + [m["name"] for m in ms]), lambda m: None)
    # presets by the app in front
    r = app.row(body, (8, 0))
    rules = app.label(body, "", 12, muted=True, wrap=860)
    def show_rules():
        rs = a.get("rules", {})
        rules.configure(text=t("Presets by app: {r}", r=", ".join(f"{e} → {p_}" for e, p_ in rs.items()))
                        if rs else t("No app rules. Add one to switch presets when an app comes to the front."))
    def add_rule():
        from tkinter import filedialog
        presets = list(a.get("presets", {}))
        if not presets:
            return rules.configure(text=t("Save a preset in the switcher first."), text_color=WARN)
        exe = filedialog.askopenfilename(filetypes=[("exe", "*.exe")])
        if exe:
            pick = ctk.CTkInputDialog(title=t("Preset"), text=t("Preset for {e} ({names}):", e=os.path.basename(exe),
                                      names=", ".join(presets))).get_input()
            if pick in presets:
                a.setdefault("rules", {})[os.path.basename(exe).lower()] = pick
                app.save()
        show_rules()
    app.button(r, t("Add app rule..."), add_rule, primary=False).pack(side="left")
    app.button(r, t("Clear rules"), lambda: (a.pop("rules", None), app.save(), show_rules()),
               primary=False).pack(side="left", padx=6)
    rules.pack(anchor="w", pady=(4, 0))
    show_rules()
    if app.__dict__.get("_ai_started"):
        return
    app._ai_started = True
    start_key()
    # game start / close
    def game_start():
        if a.get("game_unload", True):
            def work():
                names = list(running())
                for n in names:
                    ollama_unload(n)
                return names
            app.bg(work, lambda names: setattr(app, "_ai_paused", names), lambda m: None)
    def game_close():
        names = app.__dict__.pop("_ai_paused", None)
        if names and app.ask(t("AI models"), t("The game has closed. Load {names} again?", names=", ".join(names)),
                             warn=False):
            for n in names:
                app.bg(lambda n=n: load(n, a.get("keep", "-1")), None, lambda m: None)
    app.game_hooks["start"].append(game_start)
    app.game_hooks["close"].append(game_close)
    # app in front -> preset
    def watch():
        rs = a.get("rules")
        if rs:
            try:
                p_ = rs.get(_foreground_exe())
            except Exception:
                p_ = None
            if p_ and p_ != a.get("current_preset"):
                bar.use_preset(p_)
        app.after(3000, watch)
    app.after(3000, watch)
    # model at startup (Ollama may still be starting: try for a minute)
    def startup(tries=12):
        if a.get("startup"):
            app.bg(lambda: load(prepare(a["startup"], a.setdefault("models", {}).setdefault(a["startup"], {})),
                                a.get("keep", "-1")), lambda _: app.save(),
                   lambda m: tries and app.after(5000, lambda: startup(tries - 1)))
    startup()
