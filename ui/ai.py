"""AI optimization page: RAM / VRAM for local AI apps."""
from core import aitools, boost, gpuinfo, memory as mem, procs
from core.i18n import t
from .theme import ACCENT, WARN

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
    ka = app.seg(app.row(adv, 4), list(opts), lambda v: aitools.set_keep_alive(opts[v]))
    ka.set(next((k for k, v in opts.items() if v == aitools.keep_alive()), t("5 minutes (default)")))
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
        app.bg(aitools.ollama_models, fill, lambda m: msg.configure(text=t("Ollama is not running.")))
    def unload():
        for name in tree.selection():
            app.bg(lambda n=name: aitools.ollama_unload(n), lambda _: refresh(), lambda m: msg.configure(text=m))
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
        app.bg(aitools.vram_by_process, fill, lambda m: None)
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
        need = aitools.estimate(b, quants[q.get()], ctxs[c.get()])
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
