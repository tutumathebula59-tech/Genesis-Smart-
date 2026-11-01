import { useCallback, useEffect, useState } from "react";
import { C, mono } from "../../theme";

const card = { backgroundColor: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, padding: 14, marginBottom: 14 };
const btn = (primary) => ({ minHeight: 44, padding: "0 14px", borderRadius: 6, border: `1px solid ${primary ? C.cyan : C.borderLight}`,
  background: primary ? C.cyan : "transparent", color: primary ? C.bg : C.textPrimary, fontWeight: 600 });
const input = { minHeight: 44, flex: 1, minWidth: 0, padding: "0 10px", borderRadius: 6, border: `1px solid ${C.borderLight}`, background: C.bg, color: C.textPrimary };

export function WifiPanel({ authToken }) {
  const [status, setStatus] = useState(null);
  const [nets, setNets] = useState([]);
  const [clients, setClients] = useState([]);
  const [pick, setPick] = useState(null);
  const [pw, setPw] = useState("");
  const [hs, setHs] = useState({ ssid: "", password: "" });
  const [creds, setCreds] = useState(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const api = useCallback(async (path, opts = {}) => {
    const r = await fetch(`/hub/wifi${path}`, { ...opts, headers: { Authorization: `Bearer ${authToken}`, "Content-Type": "application/json" } });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || "Something went wrong");
    return body;
  }, [authToken]);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api("/status"));
      setClients(await api("/clients"));
    } catch (e) { setMsg(e.message); }
  }, [api]);

  useEffect(() => { refresh(); }, [refresh]);

  const run = async (fn, done) => {
    setBusy(true); setMsg("");
    try { await fn(); if (done) setMsg(done); await refresh(); } catch (e) { setMsg(e.message); }
    setBusy(false);
  };

  return (
    <div>
      <div style={card}>
        <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 8 }}>Wi-Fi network</div>
        {status?.devices.map((d) => (
          <div key={d.device} style={{ fontFamily: mono, fontSize: 12, color: C.textSecondary }}>
            {d.device}: {d.state}{d.connection && d.connection !== "--" ? ` (${d.connection})` : ""}
          </div>
        ))}
        <button style={{ ...btn(false), marginTop: 10 }} disabled={busy}
          onClick={() => run(async () => setNets(await api("/scan")))}>Scan for networks</button>
        {nets.map((n) => (
          <div key={n.ssid} style={{ marginTop: 8 }}>
            <button onClick={() => { setPick(n.ssid); setPw(""); }} className="tap-target"
              style={{ width: "100%", textAlign: "left", padding: "0 12px", borderRadius: 6, background: pick === n.ssid ? C.panelRaised : "transparent",
                border: `1px solid ${C.border}`, color: C.textPrimary, display: "flex", justifyContent: "space-between" }}>
              <span>{n.ssid}{n.connected ? " (connected)" : ""}</span>
              <span style={{ fontFamily: mono, fontSize: 11, color: C.textSecondary, alignSelf: "center" }}>{n.secure ? "secured" : "open"} {n.signal}%</span>
            </button>
            {pick === n.ssid && (
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                {n.secure && <input style={input} type="password" placeholder="Wi-Fi password" value={pw} onChange={(e) => setPw(e.target.value)} />}
                <button style={btn(true)} disabled={busy}
                  onClick={() => run(() => api("/connect", { method: "POST", body: JSON.stringify({ ssid: n.ssid, password: pw }) }), `Connected to ${n.ssid}`)}>Connect</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 4 }}>Hotspot</div>
        <div style={{ color: C.textSecondary, fontSize: 13, marginBottom: 10 }}>
          {status?.hotspot ? `On: devices can join "${status.hotspot_ssid}".` : "Off. Turn on to let sensors, plugs and phones join the hub directly."}
        </div>
        {!status?.hotspot && (
          <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
            <input style={input} placeholder="Hotspot name (optional)" value={hs.ssid} onChange={(e) => setHs({ ...hs, ssid: e.target.value })} />
            <input style={input} type="password" placeholder="Password, 8+ characters (optional)" value={hs.password} onChange={(e) => setHs({ ...hs, password: e.target.value })} />
          </div>
        )}
        <button style={btn(!status?.hotspot)} disabled={busy}
          onClick={() => run(async () => {
            const res = await api("/hotspot", { method: "POST", body: JSON.stringify({ enabled: !status?.hotspot, ssid: hs.ssid || null, password: hs.password || null }) });
            setCreds(res.hotspot ? res : null);
          })}>{status?.hotspot ? "Turn off hotspot" : "Turn on hotspot"}</button>
        {creds && (
          <div style={{ marginTop: 10, fontFamily: mono, fontSize: 12, color: C.amber }}>
            Name: {creds.ssid}<br />Password: {creds.password}<br />Write this down. It isn't shown again.
          </div>
        )}
        {status?.hotspot && (
          <div style={{ marginTop: 12 }}>
            <div style={{ color: C.textSecondary, fontSize: 13, marginBottom: 4 }}>{clients.length} connected</div>
            {clients.map((c) => <div key={c.mac} style={{ fontFamily: mono, fontSize: 12, color: C.textSecondary }}>{c.ip}  {c.mac}</div>)}
          </div>
        )}
      </div>
      {msg && <div style={{ color: C.amber, fontSize: 13 }}>{msg}</div>}
    </div>
  );
}
