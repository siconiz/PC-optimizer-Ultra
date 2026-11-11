"""Network checks: Wi-Fi signal and link rate (WLAN API), adapter speed, ping / loss (ICMP), DNS, speed test."""
import ctypes, os, random, socket, struct, time, urllib.request
from ctypes import wintypes
import psutil

PHY = {4: "802.11a", 5: "802.11b", 6: "802.11g", 7: "Wi-Fi 4 (802.11n)", 8: "Wi-Fi 5 (802.11ac)",
       10: "Wi-Fi 6/6E (802.11ax)", 11: "Wi-Fi 7 (802.11be)"}
DNS_SERVERS = {"Cloudflare": "1.1.1.1", "Google": "8.8.8.8", "Quad9": "9.9.9.9"}
SPEED_URL = "https://speed.cloudflare.com/__down?bytes={n}"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
DOWN_BYTES, UP_BYTES = 10_485_760, 2_000_000  # per request; uploads small enough for slow links to finish
USER_AGENT = "PCOptimizer/1.0 (+https://github.com/siconiz/PC-optimizer-Ultra)"

class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]

class IFACE(ctypes.Structure):
    _fields_ = [("guid", GUID), ("desc", ctypes.c_wchar * 256), ("state", ctypes.c_uint)]

class IFLIST(ctypes.Structure):
    _fields_ = [("n", wintypes.DWORD), ("i", wintypes.DWORD), ("items", IFACE * 64)]

class ASSOC(ctypes.Structure):
    _fields_ = [("ssid_len", ctypes.c_ulong), ("ssid", ctypes.c_ubyte * 32), ("bss_type", ctypes.c_uint),
                ("bssid", ctypes.c_ubyte * 6), ("phy", ctypes.c_uint), ("phy_index", ctypes.c_ulong),
                ("quality", ctypes.c_ulong), ("rx", ctypes.c_ulong), ("tx", ctypes.c_ulong)]

class CONN(ctypes.Structure):
    _fields_ = [("state", ctypes.c_uint), ("mode", ctypes.c_uint), ("profile", ctypes.c_wchar * 256), ("assoc", ASSOC)]

def wifi():
    """Connected Wi-Fi interfaces: ssid, signal % (0 = -100 dBm, 100 = -50 dBm), rx/tx Mbps, standard."""
    w = ctypes.windll.wlanapi
    h, ver = wintypes.HANDLE(), wintypes.DWORD()
    if w.WlanOpenHandle(2, None, ctypes.byref(ver), ctypes.byref(h)):
        return []
    out = []
    try:
        lst = ctypes.POINTER(IFLIST)()
        if w.WlanEnumInterfaces(h, None, ctypes.byref(lst)):
            return []
        for i in range(lst.contents.n):
            itf = lst.contents.items[i]
            size, data = wintypes.DWORD(), ctypes.c_void_p()
            if w.WlanQueryInterface(h, ctypes.byref(itf.guid), 7, None, ctypes.byref(size), ctypes.byref(data), None):
                continue  # 7 = wlan_intf_opcode_current_connection; fails when not connected
            a = ctypes.cast(data, ctypes.POINTER(CONN)).contents.assoc
            out.append({"adapter": itf.desc, "ssid": bytes(a.ssid[:a.ssid_len]).decode("utf-8", "replace"),
                        "signal": a.quality, "dbm": -100 + a.quality // 2, "rx": a.rx // 1000, "tx": a.tx // 1000,
                        "standard": PHY.get(a.phy, "802.11")})
            w.WlanFreeMemory(data)
        w.WlanFreeMemory(lst)
    finally:
        w.WlanCloseHandle(h, None)
    return out

def adapters():
    """Active adapters with their link speed in Mbps."""
    return [{"name": n, "mbps": s.speed} for n, s in psutil.net_if_stats().items()
            if s.isup and s.speed and "loopback" not in n.lower()]

class ECHO(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_ulong), ("status", ctypes.c_ulong), ("rtt", ctypes.c_ulong),
                ("size", ctypes.c_ushort), ("flags", ctypes.c_ushort), ("data", ctypes.c_void_p),
                ("opt", ctypes.c_ubyte * 8 if ctypes.sizeof(ctypes.c_void_p) == 4 else ctypes.c_ubyte * 16)]

def ping(host="1.1.1.1", count=20, timeout_ms=1000):
    """ICMP echo: {'avg', 'min', 'max', 'jitter', 'loss'} in ms / %."""
    ip = struct.unpack("<I", socket.inet_aton(socket.gethostbyname(host)))[0]
    icmp = ctypes.windll.iphlpapi
    icmp.IcmpCreateFile.restype = wintypes.HANDLE
    h = icmp.IcmpCreateFile()
    buf = ctypes.create_string_buffer(ctypes.sizeof(ECHO) + 64)
    rtts = []
    try:
        for _ in range(count):
            n = icmp.IcmpSendEcho(wintypes.HANDLE(h), ctypes.c_ulong(ip), b"pcoptimizer", 11, None, buf,
                                  ctypes.sizeof(buf), timeout_ms)
            r = ECHO.from_buffer(buf)
            if n and r.status == 0:
                rtts.append(r.rtt)
            time.sleep(0.1)
    finally:
        icmp.IcmpCloseHandle(wintypes.HANDLE(h))
    if not rtts:
        return {"avg": None, "min": None, "max": None, "jitter": None, "loss": 100}
    jitter = sum(abs(a - b) for a, b in zip(rtts, rtts[1:])) / max(1, len(rtts) - 1)
    return {"avg": round(sum(rtts) / len(rtts)), "min": min(rtts), "max": max(rtts), "jitter": round(jitter, 1),
            "loss": round(100 * (count - len(rtts)) / count)}

def _dns_query(server, name, timeout=2):
    q = struct.pack(">HHHHHH", random.randint(0, 65535), 0x0100, 1, 0, 0, 0)
    q += b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0" + struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t0 = time.perf_counter()
        s.sendto(q, (server, 53))
        s.recvfrom(512)
        return (time.perf_counter() - t0) * 1000

def dns_test(names=("github.com", "wikipedia.org", "microsoft.com")):
    """Average lookup time in ms for the current DNS (via Windows) and public resolvers."""
    out = {}
    t0 = time.perf_counter()
    for n in names:
        try:
            socket.getaddrinfo(f"{os.urandom(3).hex()}.{n}", 443)  # random name: not in any cache
        except OSError:  # NXDOMAIN is the expected answer
            pass
    out["Current"] = round((time.perf_counter() - t0) * 1000 / len(names))
    for label, ip in DNS_SERVERS.items():
        try:
            out[label] = round(sum(_dns_query(ip, f"{os.urandom(3).hex()}.{n}") for n in names) / len(names))
        except OSError:
            out[label] = None
    return out

def _get(url, data=None, method=None, timeout=30):
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=timeout)

def speed_test(seconds=8, streams=4):
    """Download / upload Mbps and idle latency against Cloudflare's speed test servers (speed.cloudflare.com).
    Like browser speed tests it uses several parallel connections; the first second (TCP ramp-up) is not counted."""
    import threading
    lat = []
    for _ in range(8):  # idle latency: tiny requests, median of the time to the response headers
        t0 = time.perf_counter()
        with _get(SPEED_URL.format(n=0), timeout=10) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            r.read()
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    def run(work):
        total, lock, errors = [0], threading.Lock(), []
        start = time.perf_counter()
        warm, end = start + 1.0, start + 1.0 + seconds
        def count(n):
            if time.perf_counter() >= warm:
                with lock:
                    total[0] += n
        def worker():
            while time.perf_counter() < end:
                try:
                    work(count, end)
                except Exception as e:  # keep the other streams going; report if all fail
                    errors.append(str(e))
                    time.sleep(0.2)
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(streams)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(seconds + 40)
        if not total[0] and errors:
            raise RuntimeError(errors[0])
        return round(total[0] * 8 / seconds / 1e6, 1)
    def down(count, end):
        with _get(SPEED_URL.format(n=DOWN_BYTES)) as r:
            while chunk := r.read(1 << 16):
                count(len(chunk))
                if time.perf_counter() > end:
                    break
    body = os.urandom(UP_BYTES)
    def up(count, end):
        with _get(UPLOAD_URL, data=body, method="POST") as r:
            r.read()
        count(len(body))
    return {"down": run(down), "up": run(up), "ping": round(lat[len(lat) // 2])}
