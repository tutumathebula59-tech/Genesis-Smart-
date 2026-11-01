import { useCallback, useEffect, useRef, useState } from "react";

// Live connection to the hub: device state, security log, energy, alerts.
export function useHub(token) {
  const [devices, setDevices] = useState({});
  const [events, setEvents] = useState([]);
  const [mode, setMode] = useState("disarmed");
  const [site, setSite] = useState({});
  const [cameras, setCameras] = useState([]);
  const [go2rtcPort, setGo2rtcPort] = useState(1984);
  const [ls, setLs] = useState({ slots: [], active: false });
  const [alert, setAlert] = useState(null);
  const [connected, setConnected] = useState(false);
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const api = useCallback(async (path, opts = {}) => {
    const r = await fetch(`/hub${path}`, { ...opts, headers });
    const body = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.blob();
    if (!r.ok) throw new Error(body.detail || "Request failed");
    return body;
  }, [token]); // eslint-disable-line

  const load = useCallback(async () => {
    try {
      const s = await api("/state");
      setDevices(Object.fromEntries(s.devices.map((d) => [d.id, d])));
      setMode(s.mode); setSite(s.site); setCameras(s.cameras); setGo2rtcPort(s.go2rtc_port); setLs(s.loadshedding);
      setEvents(await api("/security/events?limit=150"));
    } catch (e) { /* hub not reachable yet; socket retry will reload */ }
  }, [api]);

  useEffect(() => {
    let ws, stop = false, wait = 1000, ping;
    const open = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/hub/ws?token=${encodeURIComponent(token)}`);
      ws.onopen = () => { wait = 1000; setConnected(true); load(); ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000); };
      ws.onmessage = (e) => {
        const m = JSON.parse(e.data);
        if (m.type === "device") setDevices((d) => ({ ...d, [m.device.id]: m.device }));
        else if (m.type === "event") setEvents((ev) => [m.event, ...ev].slice(0, 300));
        else if (m.type === "alert") setAlert(m.event);
        else if (m.type === "mode") setMode(m.mode);
        else if (m.type === "energy") setSite({ ...m.site });
      };
      ws.onclose = () => { clearInterval(ping); setConnected(false); if (!stop) setTimeout(open, (wait = Math.min(wait * 2, 15000))); };
    };
    open();
    return () => { stop = true; clearInterval(ping); ws && ws.close(); };
  }, [token, load]);

  const command = (id, key, value) => api(`/devices/${encodeURIComponent(id)}/command`, { method: "POST", body: JSON.stringify({ key, value }) });
  const setSecurityMode = (m) => api("/security/mode", { method: "POST", body: JSON.stringify({ mode: m }) });

  return { devices: Object.values(devices), connected, events, mode, site, cameras, go2rtcPort, ls, alert, dismissAlert: () => setAlert(null),
    api, command, setSecurityMode, reload: load };
}

export function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
