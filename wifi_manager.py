"""
Wi-Fi + hotspot control via NetworkManager (nmcli). Linux only.

- Scan / join a Wi-Fi network from the app (no keyboard needed on the hub)
- Turn the hub into a hotspot so sensors, plugs, cameras and phones can join it
- See who is connected to the hotspot
- Fallback: if the hub has no network for ~90 s, it starts "Genesis-Setup" so you can
  connect a phone and pick the real Wi-Fi from the app.

Permissions: run the hub as a user NetworkManager allows (the logged-in desktop user
usually can), or add a polkit rule for org.freedesktop.NetworkManager.*.
Hardware note: most Wi-Fi chips cannot be a client and a hotspot on the same radio at
once. Use Ethernet as the uplink, or a second USB Wi-Fi adapter for the hotspot.
"""
import asyncio, json, re, secrets, subprocess
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

HOTSPOT_NAME = "Genesis-Hotspot"

def nm(*args, timeout=30):
    try:
        r = subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise HTTPException(501, "NetworkManager (nmcli) isn't installed on this hub")
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Network command timed out")
    if r.returncode != 0:
        raise HTTPException(400, (r.stderr or r.stdout).strip() or "Network command failed")
    return r.stdout

def fields(line):
    """nmcli -t escapes ':' as '\\:'"""
    return [p.replace("\\:", ":") for p in re.split(r"(?<!\\):", line)]

def wifi_iface(cfg):
    if cfg.get("iface"):
        return cfg["iface"]
    for line in nm("-t", "-f", "DEVICE,TYPE", "dev").splitlines():
        d, t = fields(line)[:2]
        if t == "wifi":
            return d
    raise HTTPException(404, "No Wi-Fi adapter found")

class Join(BaseModel):
    ssid: str
    password: str = ""

class Hotspot(BaseModel):
    enabled: bool
    ssid: str | None = None
    password: str | None = None

def make_router(user_dep, cfg_get, kv_get, kv_set):
    r = APIRouter(prefix="/hub/wifi")

    def cfg():
        return cfg_get()["wifi"]

    @r.get("/status")
    def status(_=Depends(user_dep)):
        devs = [dict(zip(("device", "type", "state", "connection"), fields(l)[:4]))
                for l in nm("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "dev").splitlines()]
        hotspot = any(d["connection"] == HOTSPOT_NAME and d["state"] == "connected" for d in devs)
        return {"devices": [d for d in devs if d["type"] in ("wifi", "ethernet")], "hotspot": hotspot,
                "hotspot_ssid": kv_get("hotspot_ssid", cfg()["hotspot_ssid"])}

    @r.get("/scan")
    def scan(_=Depends(user_dep)):
        out = nm("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes", "ifname", wifi_iface(cfg()), timeout=40)
        seen = {}
        for l in out.splitlines():
            use, ssid, sig, sec = (fields(l) + ["", "", "", ""])[:4]
            if ssid and (ssid not in seen or int(sig or 0) > seen[ssid]["signal"]):
                seen[ssid] = {"ssid": ssid, "signal": int(sig or 0), "secure": bool(sec.strip("-")), "connected": use == "*"}
        return sorted(seen.values(), key=lambda n: -n["signal"])

    @r.post("/connect")
    def connect(body: Join, _=Depends(user_dep)):
        if not 1 <= len(body.ssid.encode()) <= 32:
            raise HTTPException(400, "Network name must be 1-32 characters")
        if body.password and not 8 <= len(body.password) <= 63:
            raise HTTPException(400, "Wi-Fi passwords are 8-63 characters")
        args = ["dev", "wifi", "connect", body.ssid, "ifname", wifi_iface(cfg())]
        if body.password:
            args += ["password", body.password]
        nm(*args, timeout=60)
        return {"connected": body.ssid}

    @r.post("/hotspot")
    def hotspot(body: Hotspot, _=Depends(user_dep)):
        if not body.enabled:
            nm("connection", "down", HOTSPOT_NAME)
            return {"hotspot": False}
        return {"hotspot": True, **start_hotspot(body.ssid, body.password)}

    def start_hotspot(ssid=None, password=None):
        ssid = ssid or kv_get("hotspot_ssid", cfg()["hotspot_ssid"])
        password = password or cfg().get("hotspot_password") or kv_get("hotspot_password", None)
        if not password:
            password = secrets.token_urlsafe(9)   # no shipped default password
        if not 8 <= len(password) <= 63:
            raise HTTPException(400, "Hotspot password must be 8-63 characters")
        nm("dev", "wifi", "hotspot", "ifname", wifi_iface(cfg()), "con-name", HOTSPOT_NAME, "ssid", ssid, "password", password)
        nm("connection", "modify", HOTSPOT_NAME, "connection.autoconnect", "no")
        kv_set("hotspot_ssid", ssid); kv_set("hotspot_password", password)
        return {"ssid": ssid, "password": password}

    @r.get("/clients")
    def clients(_=Depends(user_dep)):
        """Devices on the hotspot (from the neighbour table)."""
        out = subprocess.run(["ip", "-j", "neigh", "show", "dev", wifi_iface(cfg())], capture_output=True, text=True).stdout
        try:
            rows = json.loads(out or "[]")
        except Exception:
            rows = []
        return [{"ip": n["dst"], "mac": n.get("lladdr"), "state": n["state"][0]} for n in rows if n.get("lladdr") and ":" not in n["dst"]]

    async def fallback_task():
        """No Ethernet/Wi-Fi uplink for ~90 s -> open the setup hotspot."""
        if not cfg().get("auto_fallback"):
            return
        down = 0
        while True:
            await asyncio.sleep(15)
            try:
                st = status()
                up = any(d["state"] == "connected" for d in st["devices"])
                down = 0 if up else down + 15
                if down >= 90 and not st["hotspot"]:
                    start_hotspot("Genesis-Setup")
                    down = -10**9   # once per outage
            except Exception:
                pass

    return r, fallback_task
