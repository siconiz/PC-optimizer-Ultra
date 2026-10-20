"""Boost profiles: while a chosen app runs, use the high performance power plan, set its priority and cores,
and (AI mode) free RAM from background apps. Everything is undone when the app closes."""
import os, threading
import psutil
from . import procs
from .i18n import t
from .power import active_scheme, pc, ultimate_scheme
from .reg import HKCU, delete, set_value

AI_APPS = {"ollama.exe": "Ollama", "ollama app.exe": "Ollama", "lm studio.exe": "LM Studio",
           "koboldcpp.exe": "KoboldCpp", "jan.exe": "Jan", "gpt4all.exe": "GPT4All"}
OLLAMA_ENV = {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_NUM_PARALLEL": "1",
              "OLLAMA_MAX_LOADED_MODELS": "1"}

def new_profile(name, exe, ai=False):
    return {"name": name, "exe": os.path.basename(exe).lower(), "plan": True,
            "priority": "Above normal" if ai else "High", "cores": "auto", "ai": ai}

def resolve_cores(mode, topo):
    if mode == "all":
        return list(range(topo["cpus"]))
    if mode == "auto":
        return topo["p"]  # performance cores on hybrid CPUs, every core otherwise
    return [c for c in mode if c < topo["cpus"]]

def set_ollama_env(on):
    for k, v in OLLAMA_ENV.items():
        set_value(HKCU, "Environment", k, v) if on else delete(HKCU, "Environment", k)

class Booster(threading.Thread):
    def __init__(self, profiles, log):
        super().__init__(daemon=True)
        self.profiles, self.log, self.stop_evt = profiles, log, threading.Event()
        self.topo = procs.topology()

    def run(self):
        target, saved, applied = ultimate_scheme(), None, set()
        self.log(t("Watching: {names}", names=", ".join(p["name"] for p in self.profiles)))
        try:
            while not self.stop_evt.wait(3):
                byexe = {p["exe"]: p for p in self.profiles}
                running = {}
                for pr in psutil.process_iter(["name"]):
                    prof = byexe.get((pr.info["name"] or "").lower())
                    if prof:
                        running.setdefault(prof["exe"], (prof, []))[1].append(pr.pid)
                for prof, pids in running.values():
                    new = [p for p in pids if p not in applied]
                    if not new:
                        continue
                    procs.set_priority(new, prof["priority"])
                    procs.set_cores(new, resolve_cores(prof["cores"], self.topo))
                    applied.update(new)
                    self.log(t("{name}: priority {pri}, cores applied", name=prof["name"], pri=t(prof["priority"])))
                    if prof.get("ai"):
                        mb = procs.free_ram(keep=[prof["exe"]])
                        self.log(t("AI mode: freed {mb} MB of RAM from background apps", mb=mb))
                want_plan = any(p.get("plan") for p, _ in running.values())
                if want_plan and saved is None:
                    saved = active_scheme()
                    pc("/setactive", target)
                    self.log(t("High performance plan on"))
                elif not want_plan and saved:
                    pc("/setactive", saved)
                    saved = None
                    self.log(t("App closed: power plan restored"))
                applied &= set(psutil.pids())
        finally:
            if saved:
                pc("/setactive", saved)
            self.log(t("Stopped"))

    def stop(self):
        self.stop_evt.set()
