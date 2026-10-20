"""Graphics driver version and age (WMI Win32_VideoController) with the vendor's download page.
GPU makers have no public "latest version" API, so freshness is judged by the driver date."""
import datetime

PAGES = {"NVIDIA": "https://www.nvidia.com/en-us/drivers/", "AMD": "https://www.amd.com/en/support/download/drivers.html",
         "Intel": "https://www.intel.com/content/www/us/en/support/detect.html"}
OLD_DAYS = 180

def drivers():
    import wmi
    out = []
    for v in wmi.WMI().Win32_VideoController():
        name = (v.Name or "").strip()
        vendor = next((k for k in PAGES if k.lower() in name.lower() or (k == "AMD" and "radeon" in name.lower())), None)
        if not vendor:
            continue
        d = str(v.DriverDate or "")[:8]
        try:
            date = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
            age = (datetime.date.today() - date).days
        except ValueError:
            date, age = None, None
        out.append({"name": name, "vendor": vendor, "version": v.DriverVersion or "-", "date": str(date or "-"),
                    "age": age, "old": age is not None and age > OLD_DAYS, "url": PAGES[vendor]})
    return out
