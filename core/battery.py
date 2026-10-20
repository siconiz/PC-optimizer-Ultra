"""Laptop battery: charge, power flow (mW from the battery driver), wear, and charger advice."""
import psutil

def status():
    """None on desktops. rate_w > 0 charging, < 0 discharging (BATTERY_STATUS.Rate is in mW)."""
    b = psutil.sensors_battery()
    if not b:
        return None
    out = {"percent": round(b.percent), "plugged": bool(b.power_plugged), "rate_w": None, "wear": None,
           "secs": b.secsleft if b.secsleft not in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) else None}
    try:
        import wmi
        w = wmi.WMI(namespace="wmi")
        s = w.BatteryStatus()[0]
        if s.Charging and s.ChargeRate:
            out["rate_w"] = round(s.ChargeRate / 1000, 1)
        elif s.Discharging and s.DischargeRate:
            out["rate_w"] = -round(s.DischargeRate / 1000, 1)
        design = w.BatteryStaticData()[0].DesignedCapacity
        full = w.BatteryFullChargedCapacity()[0].FullChargedCapacity
        if design and full:
            out["wear"] = round(full * 100 / design)  # % of the original capacity left
            out["design_wh"], out["full_wh"] = round(design / 1000, 1), round(full / 1000, 1)
    except Exception:
        pass
    return out

def advice(s):
    """Plain checks; the charger's own rating is usually not visible to Windows."""
    if not s:
        return []
    msgs = []
    if s["plugged"] and s["rate_w"] is not None and s["rate_w"] < 0:
        msgs.append("The charger is plugged in but the battery is draining: the charger gives less power than the "
                    "laptop uses. Use the laptop maker's charger with the rated wattage (or higher) for gaming.")
    if s["wear"] is not None and s["wear"] < 70:
        msgs.append("The battery holds {w}% of its original capacity. Below about 70-80% most makers consider "
                    "replacing it.")
    return msgs

CHARGER_TIPS = [
    "Barrel (round) charger: use the same voltage (V) and the same or higher wattage (W) as the original.",
    "USB-C (USB Power Delivery): up to 100 W with a 5 A cable. Laptops that need more than 100 W need a USB PD 3.1 "
    "charger and cable rated for 140-240 W.",
    "A USB-C charger with less wattage than the laptop's rating still charges, but slowly; while gaming the "
    "battery may drain even when plugged in.",
    "Gaming laptops usually reach full performance only on their barrel charger, not on USB-C.",
    "USB-C cables are rated too (60 W, 100 W / 5 A, 240 W). A 60 W cable limits a 100 W charger.",
]
