"""Charging-lag diagnostics: AC state, effective CPU clock, perf limit, temperature."""
import csv
import psutil
from .i18n import t
import win32pdh

COUNTERS = {
    "perf": r"\Processor Information(_Total)\% Processor Performance",
    "limit": r"\Processor Information(_Total)\% Performance Limit",
}
FIELDS = ["time", "plugged", "battery", "cpu_pct", "mhz", "limit_pct", "temp_c"]

class Sampler:
    def __init__(self):
        self.base = psutil.cpu_freq().current  # nominal clock on Windows
        self.q = win32pdh.OpenQuery()
        self.h = {}
        for k, p in COUNTERS.items():
            try:
                self.h[k] = win32pdh.AddEnglishCounter(self.q, p)
            except Exception:
                self.h[k] = None
        win32pdh.CollectQueryData(self.q)
        try:
            import wmi
            self.wmi = wmi.WMI(namespace="root\\wmi")
        except Exception:
            self.wmi = None
        self.rows = []

    def _read(self, key):
        try:
            return win32pdh.GetFormattedCounterValue(self.h[key], win32pdh.PDH_FMT_DOUBLE)[1]
        except Exception:
            return None

    def _temp(self):
        try:
            z = self.wmi.MSAcpi_ThermalZoneTemperature()
            return round(z[0].CurrentTemperature / 10 - 273.15, 1)
        except Exception:
            return None

    def sample(self, ts, record=True):
        win32pdh.CollectQueryData(self.q)
        perf, limit = self._read("perf"), self._read("limit")
        bat = psutil.sensors_battery()
        row = {"time": ts,
               "plugged": bat.power_plugged if bat else None,
               "battery": bat.percent if bat else None,
               "cpu_pct": psutil.cpu_percent(),
               "mhz": round(self.base * perf / 100) if perf is not None else None,
               "limit_pct": round(limit, 1) if limit is not None else None,
               "temp_c": self._temp()}
        if record:
            self.rows.append(row)
        return row

    def summary(self):
        def avg(xs):
            xs = [x for x in xs if x is not None]
            return round(sum(xs) / len(xs), 1) if xs else None
        lines = []
        for state, name in ((True, "AC"), (False, "BATTERY")):
            r = [x for x in self.rows if x["plugged"] is state]
            if r:
                lines.append(f"{name}: n={len(r)} mhz={avg(x['mhz'] for x in r)} "
                             f"limit={avg(x['limit_pct'] for x in r)} temp={avg(x['temp_c'] for x in r)}")
        lines.append(t("If the clock on AC is far below battery, the limit is under 100% and the temperature is normal, suspect BD PROCHOT or the charger."))
        return "\n".join(lines)

    def save(self, path):
        with open(path, "w", newline="") as fp:
            w = csv.DictWriter(fp, FIELDS)
            w.writeheader()
            w.writerows(self.rows)
