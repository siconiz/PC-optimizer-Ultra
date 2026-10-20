"""Temperatures, fan speeds and fan control through LibreHardwareMonitorLib (MPL-2.0) and the PawnIO driver.

PawnIO is the signed driver LibreHardwareMonitor and FanControl use instead of WinRing0 (which Defender blocks).
Without it, CPU temperatures and motherboard fans are not readable; GPU sensors still work through the GPU driver."""
import os, subprocess, sys, threading, time
from .reg import HKLM, get

UNINSTALL = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO"
PAWNIO_SRC = "https://github.com/namazso/PawnIO"
NETFX = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
SAFE_TEMP = 90  # any fan the app controls goes to 100% above this CPU / GPU temperature

def base_dir():
    root = getattr(sys, "_MEIPASS", None)
    return os.path.dirname(sys.executable) if root else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def tool(*parts):
    return os.path.join(base_dir(), "tools", *parts)

def pawnio_version():
    return get(HKLM, UNINSTALL, "DisplayVersion")

def install_pawnio():
    """Runs the official signed PawnIO installer bundled in tools (the user sees its window)."""
    subprocess.run([tool("PawnIO_setup.exe"), "-install"], check=False)
    return pawnio_version()

def curve(rule, temp):
    """Linear fan curve between (t1, p1) and (t2, p2)."""
    t1, p1, t2, p2 = (float(rule[k]) for k in ("t1", "p1", "t2", "p2"))
    if temp <= t1:
        return p1
    if temp >= t2:
        return p2
    return p1 + (p2 - p1) * (temp - t1) / (t2 - t1)

class Hardware(threading.Thread):
    """One thread owns all .NET objects. Readers use `snapshot`; fan rules come from cfg['fans']."""
    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg, self.snapshot, self.error, self.ready = cfg, [], "", threading.Event()
        self.stop_evt, self.controls = threading.Event(), {}

    def _open(self):
        # .NET Framework 4.7.2+ (release 461808) is required by LibreHardwareMonitorLib; check before loading it
        if (get(HKLM, NETFX, "Release") or 0) < 461808:
            raise RuntimeError(".NET Framework 4.7.2 or later is not installed")
        import pythonnet
        pythonnet.load("netfx")  # .NET Framework 4.8 is part of Windows 10 and 11
        import clr
        sys.path.append(tool("lhm"))  # pythonnet also resolves the library's dependencies from sys.path
        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor.Hardware import Computer
        c = Computer()
        c.IsCpuEnabled = c.IsGpuEnabled = c.IsMotherboardEnabled = c.IsControllerEnabled = True
        c.IsStorageEnabled = c.IsMemoryEnabled = True
        c.Open()
        return c

    def _read(self, computer):
        out, controls = [], {}
        def walk(hw, parent):
            hw.Update()
            for s in hw.Sensors:
                kind = str(s.SensorType)
                if kind not in ("Temperature", "Fan", "Control") and not (
                        kind in ("Clock", "Load") and str(hw.HardwareType).startswith(("Cpu", "Gpu"))):
                    continue
                sid = str(s.Identifier)
                out.append({"id": sid, "hw": parent or str(hw.Name), "hw_type": str(hw.HardwareType), "name": str(s.Name),
                            "type": kind, "value": None if s.Value is None else round(float(s.Value), 1)})
                if kind == "Control" and s.Control is not None:
                    controls[sid] = s.Control
            for sub in hw.SubHardware:
                walk(sub, str(hw.Name))
        for hw in computer.Hardware:
            walk(hw, "")
        return out, controls

    def _apply(self, snap):
        rules, temps = self.cfg.get("fans", {}), {s["id"]: s["value"] for s in snap if s["type"] == "Temperature"}
        hot = any(s["value"] and s["value"] >= SAFE_TEMP for s in snap
                  if s["type"] == "Temperature" and s["hw_type"].startswith(("Cpu", "Gpu")))
        for sid, ctl in self.controls.items():
            r = rules.get(sid, {"mode": "auto"})
            if r["mode"] == "auto":
                if str(ctl.ControlMode) == "Software":
                    ctl.SetDefault()
                continue
            want = float(r.get("value", 60)) if r["mode"] == "fixed" else \
                curve(r, temps.get(r.get("sensor"))) if temps.get(r.get("sensor")) is not None else None
            if want is None:
                ctl.SetDefault()  # the curve's sensor is gone: let the board decide
                continue
            want = 100.0 if hot else max(float(ctl.MinSoftwareValue), min(float(ctl.MaxSoftwareValue), want))
            ctl.SetSoftware(want)

    def run(self):
        try:
            computer = self._open()
        except Exception as e:
            self.error = str(e)
            self.ready.set()
            return
        try:
            while not self.stop_evt.is_set():
                try:
                    snap, self.controls = self._read(computer)
                    self._apply(snap)
                    self.snapshot = snap
                except Exception as e:
                    self.error = str(e)
                self.ready.set()
                self.stop_evt.wait(2)
        finally:
            for ctl in self.controls.values():  # give every fan back to the BIOS / driver
                try:
                    ctl.SetDefault()
                except Exception:
                    pass
            computer.Close()

    def stop(self):
        self.stop_evt.set()

    # ---- helpers for the UI ----
    def temps(self):
        return [s for s in self.snapshot if s["type"] == "Temperature"]

    def cpu_temp(self):
        cpu = [s for s in self.temps() if s["hw_type"] == "Cpu" and s["value"]]
        best = next((s for s in cpu if any(k in s["name"] for k in ("Package", "Tctl", "Tdie", "Core (Tctl"))), None)
        return (best or (max(cpu, key=lambda s: s["value"]) if cpu else {})).get("value")

    def _of(self, hw_prefix, kind):
        return [x for x in self.snapshot if x["hw_type"].startswith(hw_prefix) and x["type"] == kind
                and x["value"] is not None]

    def cores(self):
        """[(name, MHz, temp or None)] per CPU core, e.g. 'Core #1' / 'P-Core #1'."""
        temps = {x["name"]: x["value"] for x in self._of("Cpu", "Temperature")}
        return [(x["name"], round(x["value"]), temps.get(x["name"])) for x in self._of("Cpu", "Clock")
                if "Core #" in x["name"] and "Effective" not in x["name"]]

    def cpu_clock(self):
        c = [mhz for _, mhz, _ in self.cores()]
        return round(sum(c) / len(c)) if c else None

    def gpu(self):
        """(core MHz, temp) of the busiest-looking GPU from the library, or (None, None)."""
        clocks = [x for x in self._of("Gpu", "Clock") if "Core" in x["name"]]
        temps = [x for x in self._of("Gpu", "Temperature") if "Core" in x["name"] or "GPU" in x["name"]]
        return (round(clocks[0]["value"]) if clocks else None), (temps[0]["value"] if temps else None)


def acpi_temps():
    """Firmware thermal zones (no driver needed). Often a motherboard or chassis sensor, not the CPU itself."""
    import wmi
    return [{"name": z.Name.split("\\")[-1], "value": round(int(z.HighPrecisionTemperature) / 10 - 273.15, 1)}
            for z in wmi.WMI().Win32_PerfFormattedData_Counters_ThermalZoneInformation()
            if int(z.HighPrecisionTemperature or 0) > 2732]
