"""Read-only checks behind the 검사 (Check) button of the RAM and CPU widgets. It reads the hardware facts and turns
them into steps for the BIOS and the maker's pages. It never writes a setting and never calculates voltages or
timings: those depend on the exact kit and board, and a wrong value can damage the hardware."""
import re
from .i18n import t

DDR = {24: "DDR3", 26: "DDR4", 34: "DDR5"}          # SMBIOS memory type codes
UNLOCKED = re.compile(r"\d{4,5}(KF|K|X3D|XE|X)\b")  # e.g. 14700K, 13900KF, 7800X3D, 7950X

def facts():
    import wmi
    c = wmi.WMI()
    board, bios, cpu = c.Win32_BaseBoard()[0], c.Win32_BIOS()[0], c.Win32_Processor()[0]
    mods = [{"part": (m.PartNumber or "").strip(), "gb": int(m.Capacity or 0) // 2**30,
             "rated": int(m.Speed or 0), "running": int(m.ConfiguredClockSpeed or 0),
             "type": DDR.get(int(m.SMBIOSMemoryType or 0), "")} for m in c.Win32_PhysicalMemory()]
    return {"board": f"{board.Manufacturer or ''} {board.Product or ''}".strip(),
            "bios": (bios.SMBIOSBIOSVersion or "").strip(), "cpu": cpu.Name.strip(),
            "cpu_max": int(cpu.MaxClockSpeed or 0), "mods": mods}

def ram_advice(f):
    mods = f["mods"]
    if not mods:
        return [t("No memory information")]
    out = []
    if len(mods) == 1:
        out.append(t("One memory module: add a second identical module (same size, speed and kit) to run dual channel."))
    elif len(mods) == 4:
        out.append(t("Four modules often run slower than two, especially DDR5. Check the board's memory list."))
    running = min(m["running"] for m in mods)
    rated = max(m["rated"] for m in mods)
    if rated and running < rated:
        out.append(t("Runs below the speed the module reports: enable the XMP (Intel) or EXPO (AMD) profile in BIOS."))
    elif rated and running > rated:
        out.append(t("Runs above the speed the module reports: a profile or overclock is on. Test stability with a memory test."))
    else:
        out.append(t("Runs at the speed the module reports. If the kit has an XMP/EXPO profile, enable it in BIOS and compare."))
    for part in sorted({m["part"] for m in mods if m["part"]}):
        out.append(t("Look up {part} on the maker's spec page for its XMP/EXPO speed, timings and voltage.", part=part))
    out.append(t("Enter only values from the official pages. This app does not calculate or write them."))
    out.append(t("If the profile is missing in BIOS, update the BIOS from {board}'s support page (now {bios}).",
                 board=f["board"] or "-", bios=f["bios"] or "-"))
    return out

def cpu_advice(f):
    out = []
    if UNLOCKED.search(f["cpu"]):
        out.append(t("Unlocked processor: the multiplier can be changed with Intel XTU (Z-series board only) or AMD Ryzen Master."))
    else:
        out.append(t("Locked processor: the multiplier cannot be raised. Keep the default settings; boost works on its own."))
    out.append(t("Check temperatures under full load first. If they are near the limit, improve cooling before changing clocks or voltage."))
    out.append(t("Change one setting at a time and run a stress test after each change."))
    out.append(t("Look up {cpu} on the maker's spec page for its official limits. This app does not calculate them.", cpu=f["cpu"]))
    return out
