"""
Genesis hub core. Everything runs locally; the internet is optional.

  Zigbee  -> Zigbee2MQTT   (MQTT)
  Z-Wave  -> Z-Wave JS UI  (MQTT)
  Matter  -> python-matter-server (WebSocket)
  Cameras -> go2rtc (live view) + optional Frigate (person/motion events)
  Alerts  -> WebSocket (touchpad / app) + ntfy push (self-hostable, works on LAN)

Run:  uvicorn hub_core:app --host 0.0.0.0 --port 8000
Data lives in $GENESIS_DATA (default ./data): hub.db, config.json, backups/.
"""
import asyncio, csv, io, json, os, secrets, sqlite3, tarfile, threading, time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import jwt
import paho.mqtt.client as mqtt
import websockets
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from wifi_manager import make_router as make_wifi
from auth_backend import JWT_ALGO, JWT_SECRET, router as auth_router

try:
    from assistant_backend import router as assistant_router
except Exception:  # no ANTHROPIC_API_KEY / offline: the app falls back to its local parser
    assistant_router = None

DATA = Path(os.environ.get("GENESIS_DATA", "./data"))
(DATA / "backups").mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------- config
DEFAULTS = json.loads((Path(__file__).parent / "config.example.json").read_text())

def load_cfg():
    cfg = json.loads(json.dumps(DEFAULTS))
    p = DATA / "config.json"
    if p.exists():
        for k, v in json.loads(p.read_text()).items():
            cfg[k] = {**cfg.get(k, {}), **v} if isinstance(v, dict) else v
    return cfg

CFG = load_cfg()

# --------------------------------------------------------------------- db
_db = sqlite3.connect(DATA / "hub.db", check_same_thread=False)
_db.row_factory = sqlite3.Row
_lock = threading.Lock()
_db.executescript("""
CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, name TEXT, protocol TEXT, native TEXT, kind TEXT,
  state TEXT DEFAULT '{}', online INTEGER DEFAULT 1, essential INTEGER DEFAULT 1, sheddable INTEGER DEFAULT 0, updated REAL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, severity TEXT, device_id TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS samples(ts INTEGER, source TEXT, metric TEXT, value REAL);
CREATE INDEX IF NOT EXISTS ix_samples ON samples(ts);
CREATE INDEX IF NOT EXISTS ix_events ON events(ts);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
""")

def q(sql, args=(), write=False):
    with _lock:
        cur = _db.execute(sql, args)
        if write:
            _db.commit()
        return cur.fetchall()

def kv_get(key, default=None):
    r = q("SELECT value FROM kv WHERE key=?", (key,))
    return json.loads(r[0]["value"]) if r else default

def kv_set(key, value):
    q("INSERT INTO kv VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)), True)

def dev_row(r):
    d = dict(r)
    d["state"] = json.loads(d["state"] or "{}")
    return d

def get_dev(dev_id):
    r = q("SELECT * FROM devices WHERE id=?", (dev_id,))
    if not r:
        raise HTTPException(404, "Unknown device")
    return dev_row(r[0])

# ------------------------------------------------------------- live state
LOOP: asyncio.AbstractEventLoop | None = None
CLIENTS: set[WebSocket] = set()
SITE: dict = {}          # latest solar / battery / grid / load readings
MQTT: mqtt.Client | None = None
MATTER_WS = None

async def _bcast(msg):
    dead = []
    for ws in list(CLIENTS):
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        CLIENTS.discard(ws)

def broadcast(msg):
    if LOOP:
        asyncio.run_coroutine_threadsafe(_bcast(msg), LOOP)

# ------------------------------------------------------- events & alerts
SEVERITIES = ("info", "warn", "alert", "critical")

def emit(kind, severity, message, device_id=None):
    ts = time.time()
    q("INSERT INTO events(ts,kind,severity,device_id,message) VALUES(?,?,?,?,?)", (ts, kind, severity, device_id, message), True)
    ev = {"ts": ts, "kind": kind, "severity": severity, "device_id": device_id, "message": message}
    broadcast({"type": "event", "event": ev})
    if severity in ("alert", "critical"):
        broadcast({"type": "alert", "event": ev})
        threading.Thread(target=_push_phone, args=(message, severity), daemon=True).start()
        siren = CFG["alerts"].get("siren_device")
        if siren and severity == "critical" and LOOP:
            asyncio.run_coroutine_threadsafe(_siren(siren), LOOP)

def _push_phone(message, severity):
    """ntfy: install the ntfy app, subscribe to the topic. Self-host ntfy on the hub to keep alerts LAN-only."""
    a = CFG["alerts"]
    try:
        httpx.post(f"{a['ntfy_url'].rstrip('/')}/{a['ntfy_topic']}", content=message.encode(), timeout=5,
                   headers={"Title": "Genesis security", "Priority": "urgent" if severity == "critical" else "high", "Tags": "rotating_light"})
    except Exception:
        pass  # offline or ntfy down: the in-app alert already fired

async def _siren(dev_id):
    try:
        await command(dev_id, "on", True)
        await asyncio.sleep(CFG["alerts"].get("siren_seconds", 120))
        await command(dev_id, "on", False)
    except Exception:
        pass

def mode():
    return kv_get("security_mode", "disarmed")   # disarmed | home | night | away

def rules(dev, old, new):
    k, name, m = dev["kind"], dev["name"], mode()
    if k in ("door", "window") and new.get("open") != old.get("open") and "open" in new:
        if new["open"]:
            emit("contact", "alert" if m in ("away", "night") else "info", f"{name} opened", dev["id"])
        else:
            emit("contact", "info", f"{name} closed", dev["id"])
    if k == "motion" and new.get("motion") and not old.get("motion"):
        emit("motion", "alert" if m == "away" else "info", f"Motion: {name}", dev["id"])
    if k in ("smoke", "leak") and new.get("alarm") and not old.get("alarm"):
        emit(k, "critical", f"{'Smoke' if k == 'smoke' else 'Water leak'} detected: {name}", dev["id"])
    if k == "lock" and "locked" in new and new.get("locked") != old.get("locked"):
        emit("lock", "info", f"{name} {'locked' if new['locked'] else 'unlocked'}", dev["id"])
    if new.get("tamper") and not old.get("tamper"):
        emit("tamper", "alert", f"Tamper: {name}", dev["id"])
    b = new.get("battery")
    if b is not None and b < 15 and (old.get("battery") is None or old["battery"] >= 15):
        emit("battery", "warn", f"Low battery ({b}%): {name}", dev["id"])

def update_device(dev_id, name, protocol, native, kind, patch):
    r = q("SELECT * FROM devices WHERE id=?", (dev_id,))
    if r:
        d = dev_row(r[0])
        old = dict(d["state"])
        d["state"].update(patch)
        kind = d["kind"] if d["kind"] != "unknown" else kind
    else:
        old, d = {}, {"id": dev_id, "name": name, "protocol": protocol, "native": native, "kind": kind, "state": dict(patch), "online": 1}
        q("INSERT INTO devices(id,name,protocol,native,kind,state,updated) VALUES(?,?,?,?,?,?,?)",
          (dev_id, name, protocol, native, kind, "{}", time.time()), True)
    q("UPDATE devices SET state=?, kind=?, online=1, updated=? WHERE id=?", (json.dumps(d["state"]), kind, time.time(), dev_id), True)
    d["kind"] = kind
    broadcast({"type": "device", "device": get_dev(dev_id)})
    rules(d, old, d["state"])

def set_online(dev_id, online):
    q("UPDATE devices SET online=? WHERE id=?", (1 if online else 0, dev_id), True)
    try:
        d = get_dev(dev_id)
        broadcast({"type": "device", "device": d})
        if not online:
            emit("offline", "warn", f"{d['name']} went offline", dev_id)
    except HTTPException:
        pass

# ------------------------------------------------------------- Zigbee
def handle_z2m(topic, raw):
    base = CFG["mqtt"]["z2m_base"]
    rest = topic[len(base) + 1:]
    if rest.startswith("bridge"):
        return
    if rest.endswith("/availability"):
        try:
            set_online(f"zigbee:{rest[:-13]}", json.loads(raw).get("state") == "online")
        except Exception:
            pass
        return
    if "/" in rest:
        return
    try:
        p = json.loads(raw)
        assert isinstance(p, dict)
    except Exception:
        return
    name, kind, patch = rest, "unknown", {}
    if "contact" in p:
        kind, patch["open"] = ("window" if "window" in name.lower() else "door"), not p["contact"]
    elif "occupancy" in p or "presence" in p:
        kind, patch["motion"] = "motion", bool(p.get("occupancy", p.get("presence")))
    elif "water_leak" in p:
        kind, patch["alarm"] = "leak", bool(p["water_leak"])
    elif "smoke" in p:
        kind, patch["alarm"] = "smoke", bool(p["smoke"])
    elif "lock_state" in p or p.get("state") in ("LOCK", "UNLOCK"):
        kind = "lock"
        patch["locked"] = p.get("lock_state") == "locked" or p.get("state") == "LOCK"
    elif "local_temperature" in p:
        kind = "thermostat"
        patch.update(temperature=p["local_temperature"], mode=p.get("system_mode"),
                     setpoint=p.get("occupied_heating_setpoint", p.get("occupied_cooling_setpoint")))
    elif "power" in p and "state" in p:
        kind = "plug"
        patch.update(on=p["state"] == "ON", power_w=p["power"])
    elif "state" in p:
        kind = "light" if "brightness" in p else "switch"
        patch["on"] = p["state"] == "ON"
        if "brightness" in p:
            patch["brightness"] = p["brightness"]
    for src, dst in (("battery", "battery"), ("tamper", "tamper"), ("temperature", "temperature"), ("humidity", "humidity")):
        if src in p:
            patch[dst] = p[src]
    if patch:
        update_device(f"zigbee:{name}", name, "zigbee", name, kind, patch)

# ------------------------------------------------------------- Z-Wave
# zwave-js-ui "named topics": zwave/<node>/<commandclass>/endpoint_0/<property>
# Property names depend on your gateway settings; extend this table to match what you see in the MQTT explorer.
ZWAVE_MAP = {
    ("switch_binary", "currentValue"): ("plug", "on", bool),
    ("lock", "locked"): ("lock", "locked", bool),
    ("sensor_binary", "Door-Window"): ("door", "open", bool),
    ("sensor_binary", "Motion"): ("motion", "motion", bool),
    ("meter", "value/66049"): ("plug", "power_w", float),       # Electric_W
    ("battery", "level"): (None, "battery", float),
}

def handle_zwave(topic, raw):
    parts = topic[len(CFG["mqtt"]["zwave_base"]) + 1:].split("/")
    if len(parts) < 4 or parts[0].startswith("_"):
        return
    node, cc, prop = parts[0], parts[1], "/".join(parts[3:])
    m = ZWAVE_MAP.get((cc, prop))
    if not m:
        return
    try:
        val = json.loads(raw)
        val = val.get("value") if isinstance(val, dict) else val
    except Exception:
        return
    kind, key, cast = m
    if val is None:
        return
    update_device(f"zwave:{node}", node, "zwave", node, kind or "unknown", {key: cast(val)})

# -------------------------------------------------------------- Matter
# Cluster ids: OnOff=6, DoorLock=257, BooleanState=69, Occupancy=1030, Thermostat=513, ElectricalPower=144
async def matter_task():
    global MATTER_WS
    cfg = CFG["matter"]
    while cfg.get("enabled"):
        try:
            async with websockets.connect(cfg["url"]) as ws:
                MATTER_WS = ws
                await ws.send(json.dumps({"message_id": "start", "command": "start_listening"}))
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("message_id") == "start":
                        for node in msg.get("result", []):
                            for path, v in node.get("attributes", {}).items():
                                matter_attr(node["node_id"], path, v, node.get("attributes", {}))
                    elif msg.get("event") == "attribute_updated":
                        node_id, path, v = msg["data"]
                        matter_attr(node_id, path, v, {})
        except Exception:
            MATTER_WS = None
            await asyncio.sleep(10)   # server not running: retry quietly

def matter_attr(node, path, v, attrs):
    ep, cl, at = (int(x) for x in path.split("/"))
    name = attrs.get(f"0/40/5") or f"Matter node {node}"
    did = f"matter:{node}"
    if (cl, at) == (6, 0):
        update_device(did, name, "matter", str(node), "plug", {"on": bool(v)})
    elif (cl, at) == (257, 0):
        update_device(did, name, "matter", str(node), "lock", {"locked": v == 1})
    elif (cl, at) == (69, 0):
        update_device(did, name, "matter", str(node), "door", {"open": not v})
    elif (cl, at) == (1030, 0):
        update_device(did, name, "matter", str(node), "motion", {"motion": bool(v and (v & 1))})
    elif cl == 513 and at == 0 and v is not None:
        update_device(did, name, "matter", str(node), "thermostat", {"temperature": v / 100})
    elif cl == 513 and at == 18 and v is not None:
        update_device(did, name, "matter", str(node), "thermostat", {"setpoint": v / 100})
    elif (cl, at) == (144, 8) and v is not None:
        update_device(did, name, "matter", str(node), "plug", {"power_w": v / 1000})

async def matter_cmd(node, cluster, name, payload=None, endpoint=1):
    if not MATTER_WS:
        raise HTTPException(503, "Matter server not connected")
    await MATTER_WS.send(json.dumps({"message_id": secrets.token_hex(4), "command": "device_command",
        "args": {"node_id": int(node), "endpoint_id": endpoint, "cluster_id": cluster, "command_name": name, "payload": payload or {}}}))

# ------------------------------------------------------------ commands
ALLOWED_KEYS = {"on", "locked", "brightness", "setpoint", "mode"}

async def command(dev_id, key, value):
    if key not in ALLOWED_KEYS:
        raise HTTPException(400, f"Can't set '{key}'")
    d = get_dev(dev_id)
    proto, native, st = d["protocol"], d["native"], d["state"]
    if proto == "zigbee":
        z = CFG["mqtt"]["z2m_base"]
        if key == "on":
            body = {"state": "ON" if value else "OFF"}
        elif key == "locked":
            body = {"state": "LOCK" if value else "UNLOCK"}
        elif key == "brightness":
            body = {"brightness": int(value)}
        elif key == "setpoint":
            field = "occupied_cooling_setpoint" if st.get("mode") == "cool" else "occupied_heating_setpoint"
            body = {field: float(value)}
        else:
            body = {"system_mode": str(value)}
        MQTT.publish(f"{z}/{native}/set", json.dumps(body))
    elif proto == "zwave":
        w = CFG["mqtt"]["zwave_base"]
        topics = {"on": ("switch_binary", "currentValue", bool(value)), "locked": ("lock", "targetMode", 255 if value else 0)}
        if key not in topics:
            raise HTTPException(400, "Not supported for Z-Wave devices")
        cc, prop, v = topics[key]
        MQTT.publish(f"{w}/{native}/{cc}/endpoint_0/{prop}/set", json.dumps(v))
    elif proto == "matter":
        if key == "on":
            await matter_cmd(native, 6, "On" if value else "Off")
        elif key == "locked":
            await matter_cmd(native, 257, "LockDoor" if value else "UnlockDoor")
        else:
            raise HTTPException(400, "Not supported for Matter devices yet")
    else:
        raise HTTPException(400, "Unknown protocol")
    # optimistic update; the device's own report will confirm or correct it
    update_device(dev_id, d["name"], proto, native, d["kind"], {key: value})
    emit("command", "info", f"{d['name']}: {key} -> {value}", dev_id)
    return {"ok": True}

def command_sync(dev_id, key, value):
    """For assistant_backend.apply_control_device (runs in a worker thread)."""
    return asyncio.run_coroutine_threadsafe(command(dev_id, key, value), LOOP).result(10)

# ---------------------------------------------------------- MQTT glue
def _num(raw):
    try:
        v = json.loads(raw)
        v = v.get("value") if isinstance(v, dict) else v
        return float(v) if not isinstance(v, bool) else v
    except Exception:
        return None

def start_mqtt():
    global MQTT
    c = CFG["mqtt"]
    cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if c.get("user"):
        cl.username_pw_set(c["user"], c.get("password", ""))
    energy_topics = {v: k for k, v in CFG["energy"]["topics"].items() if v}

    def on_connect(client, ud, flags, rc, props):
        for t in (f"{c['z2m_base']}/#", f"{c['zwave_base']}/#", f"{c['frigate_base']}/events", *energy_topics):
            client.subscribe(t)

    def on_message(client, ud, msg):
        t, raw = msg.topic, msg.payload.decode(errors="ignore")
        try:
            if t in energy_topics:
                key, v = energy_topics[t], _num(raw)
                if v is None:
                    return
                if key == "grid_ok":
                    was = SITE.get("grid_ok")
                    SITE["grid_ok"] = bool(v)
                    if was is True and not v:
                        emit("grid", "warn", "Grid power lost, running on battery")
                    elif was is False and v:
                        emit("grid", "info", "Grid power restored")
                else:
                    SITE[key] = v
                broadcast({"type": "energy", "site": SITE})
            elif t.startswith(c["z2m_base"] + "/"):
                handle_z2m(t, raw)
            elif t.startswith(c["zwave_base"] + "/"):
                handle_zwave(t, raw)
            elif t == f"{c['frigate_base']}/events":
                e = json.loads(raw)
                if e.get("type") == "new":
                    a = e["after"]
                    emit("camera", "alert" if a.get("label") == "person" and mode() == "away" else "info",
                         f"{a.get('label', 'Object').capitalize()} on {a.get('camera')} camera")
        except Exception as ex:
            print("[mqtt]", t, ex)

    cl.on_connect, cl.on_message = on_connect, on_message
    cl.reconnect_delay_set(1, 30)
    try:
        cl.connect_async(c["host"], c["port"])
        cl.loop_start()
    except Exception as ex:
        print("[mqtt] not started:", ex)
    MQTT = cl

# -------------------------------------------------------------- energy
async def energy_task():
    interval = CFG["energy"]["interval_s"]
    while True:
        await asyncio.sleep(interval)
        ts = int(time.time())
        rows = [(ts, "site", k, v) for k, v in SITE.items() if isinstance(v, (int, float)) and not isinstance(v, bool)]
        for r in q("SELECT id,state FROM devices"):
            w = json.loads(r["state"]).get("power_w")
            if w is not None:
                rows.append((ts, r["id"], "power_w", float(w)))
        with _lock:
            _db.executemany("INSERT INTO samples VALUES(?,?,?,?)", rows)
            _db.commit()

def month_report(month):
    start = datetime.strptime(month, "%Y-%m")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    k = CFG["energy"]["interval_s"] / 3_600_000  # W per sample -> kWh
    rows = q("""SELECT source, metric, SUM(MAX(value,0)) pos, SUM(MIN(value,0)) neg FROM samples
                WHERE ts>=? AND ts<? AND metric!='battery_soc' GROUP BY source, metric""", (start.timestamp(), end.timestamp()))
    site = {r["metric"]: r for r in rows if r["source"] == "site"}
    kwh = lambda m, side="pos": round((site[m][side] if m in site else 0) * k, 2) * (1 if side == "pos" else -1)
    names = {r["id"]: r["name"] for r in q("SELECT id,name FROM devices")}
    per_dev = sorted(({"id": r["source"], "name": names.get(r["source"], r["source"]), "kwh": round(r["pos"] * k, 2)}
                      for r in rows if r["source"] != "site" and r["metric"] == "power_w"), key=lambda x: -x["kwh"])
    solar, imp, exp = kwh("solar_w"), kwh("grid_w"), kwh("grid_w", "neg")
    tariff = CFG["energy"]["tariff_per_kwh"]
    return {"month": month, "currency": CFG["energy"]["currency"], "tariff": tariff,
            "solar_kwh": solar, "load_kwh": kwh("load_w"), "grid_import_kwh": imp, "grid_export_kwh": exp,
            "battery_charge_kwh": kwh("battery_w"), "battery_discharge_kwh": kwh("battery_w", "neg"),  # + = charging
            "grid_cost": round(imp * tariff, 2), "solar_savings": round(max(solar - exp, 0) * tariff, 2),
            "devices": per_dev}

# ------------------------------------------------------- load shedding
def load_slots():
    p = DATA / "loadshedding.json"
    return json.loads(p.read_text()).get("slots", []) if p.exists() else []

def save_slots(slots):
    (DATA / "loadshedding.json").write_text(json.dumps({"slots": slots, "updated": time.time()}))

def refresh_esp():
    """Optional online refresh (EskomSePush). Cached to disk so everything works offline afterwards.
    Check the current API URL/terms at https://esp.info before relying on this."""
    c = CFG["loadshedding"]
    if c["provider"] != "eskomsepush" or not c["esp_token"]:
        return
    try:
        r = httpx.get("https://developer.sepush.co.za/business/2.0/area", params={"id": c["esp_area_id"]},
                      headers={"Token": c["esp_token"]}, timeout=10).json()
        slots = [{"start": e["start"][:19], "end": e["end"][:19], "stage": e.get("note", "")} for e in r.get("events", [])]
        save_slots(slots)
    except Exception:
        pass

async def loadshedding_task():
    c = CFG["loadshedding"]
    last_refresh = 0
    while True:
        await asyncio.sleep(30)
        try:
            if time.time() - last_refresh > 6 * 3600:
                last_refresh = time.time()
                await asyncio.to_thread(refresh_esp)
            now, pre = datetime.now(), timedelta(minutes=c["pre_action_minutes"])
            cur = next((s for s in load_slots()
                        if datetime.fromisoformat(s["start"]) - pre <= now < datetime.fromisoformat(s["end"])), None)
            restore = kv_get("ls_restore", None)
            if cur and restore is None:
                restore = {}
                for did in c["shed_devices"]:
                    restore[did] = get_dev(did)["state"].get("on", False)
                    await command(did, "on", False)
                for did in c["thermostats"]:
                    sp = get_dev(did)["state"].get("setpoint")
                    if sp is not None:
                        restore[f"sp:{did}"] = sp
                        await command(did, "setpoint", sp - c["thermostat_setback"])
                kv_set("ls_restore", restore)
                emit("loadshedding", "warn", f"Load shedding {cur['start'][11:16]}-{cur['end'][11:16]}: non-essential loads off")
            elif cur and restore is not None and SITE.get("battery_soc", 100) < c["battery_min_soc"]:
                for did in c["shed_if_battery_below"]:
                    if did not in restore:
                        restore[did] = get_dev(did)["state"].get("on", False)
                        await command(did, "on", False)
                        emit("loadshedding", "warn", f"Battery {SITE['battery_soc']:.0f}%: switched off {get_dev(did)['name']}")
                kv_set("ls_restore", restore)
            elif not cur and restore is not None:
                for did, prev in restore.items():
                    if did.startswith("sp:"):
                        await command(did[3:], "setpoint", prev)
                    elif prev:
                        await command(did, "on", True)
                kv_set("ls_restore", None)
                emit("loadshedding", "info", "Load shedding over: loads restored")
        except Exception as ex:
            print("[loadshedding]", ex)

# -------------------------------------------------------------- backup
def backup_now(label="auto"):
    name = f"genesis-{datetime.now():%Y%m%d-%H%M%S}-{label}.tar.gz"
    tmp = DATA / "hub.snapshot.db"
    with _lock:
        dst = sqlite3.connect(tmp)
        _db.backup(dst)
        dst.close()
    out = DATA / "backups" / name
    with tarfile.open(out, "w:gz") as t:
        t.add(tmp, arcname="hub.db")
        for f in ("config.json", "loadshedding.json"):
            if (DATA / f).exists():
                t.add(DATA / f, arcname=f)
    tmp.unlink()
    for old in sorted((DATA / "backups").glob("genesis-*.tar.gz"))[:-CFG["backup"]["keep"]]:
        old.unlink()
    usb = CFG["backup"].get("usb_path")
    if usb and Path(usb).is_dir():
        (Path(usb) / name).write_bytes(out.read_bytes())
    return name

async def backup_task():
    done = None
    while True:
        await asyncio.sleep(60)
        n = datetime.now()
        if n.hour == CFG["backup"]["hour"] and done != n.date():
            done = n.date()
            await asyncio.to_thread(backup_now)
            emit("backup", "info", "Nightly backup complete")

# ------------------------------------------------------------ cameras
def write_go2rtc():
    lines = ["streams:"] + [f"  {c['id']}: {c['rtsp']}" for c in CFG["cameras"]]
    lines += ["api:", f"  listen: \":{CFG['go2rtc_port']}\"", "webrtc:", "  listen: \":8555\""]
    (DATA / "go2rtc.yaml").write_text("\n".join(lines) + "\n")   # run: go2rtc -config data/go2rtc.yaml

# ----------------------------------------------------------------- API
def user(authorization: str | None = Header(None), token: str | None = Query(None)):
    t = token or (authorization or "").removeprefix("Bearer ").strip()
    try:
        return jwt.decode(t, JWT_SECRET, algorithms=[JWT_ALGO])["sub"]
    except Exception:
        raise HTTPException(401, "Sign in again")

hub = APIRouter(prefix="/hub")

class Cmd(BaseModel):
    key: str
    value: bool | int | float | str

class Patch(BaseModel):
    name: str | None = None
    essential: bool | None = None
    sheddable: bool | None = None

class Mode(BaseModel):
    mode: str

@hub.get("/state")
def state(_=Depends(user)):
    return {"devices": [dev_row(r) for r in q("SELECT * FROM devices ORDER BY name")], "mode": mode(), "site": SITE,
            "cameras": [{"id": c["id"], "name": c["name"]} for c in CFG["cameras"]], "go2rtc_port": CFG["go2rtc_port"],
            "loadshedding": {"slots": [s for s in load_slots() if datetime.fromisoformat(s["end"]) > datetime.now()][:8],
                             "active": kv_get("ls_restore", None) is not None}}

@hub.post("/devices/{dev_id:path}/command")
async def cmd(dev_id: str, body: Cmd, _=Depends(user)):
    return await command(dev_id, body.key, body.value)

@hub.patch("/devices/{dev_id:path}")
def patch_dev(dev_id: str, body: Patch, _=Depends(user)):
    get_dev(dev_id)
    for col, v in (("name", body.name), ("essential", body.essential), ("sheddable", body.sheddable)):
        if v is not None:
            q(f"UPDATE devices SET {col}=? WHERE id=?", (v, dev_id), True)
    return get_dev(dev_id)

@hub.post("/security/mode")
def set_mode(body: Mode, who=Depends(user)):
    if body.mode not in ("disarmed", "home", "night", "away"):
        raise HTTPException(400, "Unknown mode")
    kv_set("security_mode", body.mode)
    emit("mode", "info", f"Security set to {body.mode}")
    broadcast({"type": "mode", "mode": body.mode})
    return {"mode": body.mode}

@hub.get("/security/events")
def events(limit: int = 200, min_severity: str = "info", kind: str | None = None, _=Depends(user)):
    sev = SEVERITIES[SEVERITIES.index(min_severity):] if min_severity in SEVERITIES else SEVERITIES
    sql = f"SELECT * FROM events WHERE severity IN ({','.join('?' * len(sev))})" + (" AND kind=?" if kind else "") + " ORDER BY ts DESC LIMIT ?"
    return [dict(r) for r in q(sql, (*sev, *([kind] if kind else []), min(limit, 1000)))]

@hub.get("/energy/report")
def report(month: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m")), _=Depends(user)):
    return month_report(month)

@hub.get("/energy/report.csv")
def report_csv(month: str = Query(default_factory=lambda: datetime.now().strftime("%Y-%m")), _=Depends(user)):
    r, out = month_report(month), io.StringIO()
    w = csv.writer(out)
    w.writerow(["Genesis energy report", month])
    for k in ("solar_kwh", "load_kwh", "grid_import_kwh", "grid_export_kwh", "battery_charge_kwh", "battery_discharge_kwh", "grid_cost", "solar_savings"):
        w.writerow([k, r[k]])
    w.writerow([]); w.writerow(["device", "kwh"])
    for d in r["devices"]:
        w.writerow([d["name"], d["kwh"]])
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=energy-{month}.csv"})

@hub.get("/loadshedding")
def get_ls(_=Depends(user)):
    return {"config": CFG["loadshedding"], "slots": load_slots()}

@hub.put("/loadshedding")
def put_ls(slots: list[dict], _=Depends(user)):
    """Offline entry: [{"start":"2026-10-30T18:00:00","end":"2026-10-30T20:30:00","stage":2}]"""
    for s in slots:
        datetime.fromisoformat(s["start"]); datetime.fromisoformat(s["end"])
    save_slots(slots)
    return {"saved": len(slots)}

@hub.post("/backup")
async def do_backup(_=Depends(user)):
    return {"name": await asyncio.to_thread(backup_now, "manual")}

@hub.get("/backups")
def list_backups(_=Depends(user)):
    return [{"name": p.name, "bytes": p.stat().st_size, "ts": p.stat().st_mtime} for p in sorted((DATA / "backups").glob("*.tar.gz"), reverse=True)]

@hub.get("/backups/{name}")
def dl_backup(name: str, _=Depends(user)):
    p = DATA / "backups" / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, filename=p.name)

@hub.post("/backups/{name}/restore")
def restore(name: str, _=Depends(user)):
    p = DATA / "backups" / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    backup_now("pre-restore")
    with tarfile.open(p) as t:
        for m in t.getmembers():
            if m.name in ("hub.db", "config.json", "loadshedding.json"):
                t.extract(m, DATA / "restore-staging", filter="data")
    return {"staged": True, "next": "Stop the hub, copy data/restore-staging/* over data/, then start it again."}

@hub.websocket("/ws")
async def ws(sock: WebSocket, token: str = ""):
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        await sock.close(code=4401)
        return
    await sock.accept()
    CLIENTS.add(sock)
    try:
        while True:
            await sock.receive_text()   # keep-alive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        CLIENTS.discard(sock)

# ----------------------------------------------------------------- app
@asynccontextmanager
async def lifespan(app):
    global LOOP
    if JWT_SECRET == "change-me-in-production" and not os.environ.get("GENESIS_DEV"):
        raise RuntimeError("Set JWT_SECRET before starting the hub (or GENESIS_DEV=1 for local testing).")
    LOOP = asyncio.get_running_loop()
    write_go2rtc()
    start_mqtt()
    tasks = [asyncio.create_task(f()) for f in (matter_task, energy_task, loadshedding_task, backup_task, wifi_fallback)]
    yield
    for t in tasks:
        t.cancel()
    if MQTT:
        MQTT.loop_stop()

wifi_router, wifi_fallback = make_wifi(user, lambda: CFG, kv_get, kv_set)
app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)
if assistant_router:
    app.include_router(assistant_router)
app.include_router(hub)
app.include_router(wifi_router)
if Path("dist").is_dir():
    app.mount("/", StaticFiles(directory="dist", html=True), name="pwa")
