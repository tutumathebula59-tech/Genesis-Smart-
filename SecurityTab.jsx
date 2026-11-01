import { useState } from "react";
import { C, mono } from "../../theme";

const card = { backgroundColor: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, padding: 14, marginBottom: 14 };
const MODES = [["disarmed", "Off"], ["home", "Home"], ["night", "Night"], ["away", "Away"]];
const SENSOR_KINDS = ["door", "window", "motion", "smoke", "leak"];
const SEV = { info: C.textDim, warn: C.amber, alert: C.red, critical: C.red };

function sensorText(d) {
  const s = d.state;
  if (!d.online) return ["Offline", C.textDim];
  if (d.kind === "door" || d.kind === "window") return s.open ? ["Open", C.amber] : ["Closed", C.green];
  if (d.kind === "motion") return s.motion ? ["Motion", C.amber] : ["Clear", C.green];
  return s.alarm ? ["ALARM", C.red] : ["OK", C.green];
}

export function SecurityTab({ hub }) {
  const [filter, setFilter] = useState("info");
  const sensors = hub.devices.filter((d) => SENSOR_KINDS.includes(d.kind));
  const locks = hub.devices.filter((d) => d.kind === "lock");
  const shown = hub.events.filter((e) => filter === "info" || ["alert", "critical"].includes(e.severity));
  const btn = (on) => ({ flex: 1, minHeight: 48, borderRadius: 6, border: `1px solid ${on ? C.cyan : C.borderLight}`, background: on ? C.cyan : "transparent", color: on ? C.bg : C.textPrimary, fontWeight: 600 });

  return (
    <div>
      <div style={card}>
        <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 4 }}>Alarm mode</div>
        <div style={{ color: C.textSecondary, fontSize: 13, marginBottom: 10 }}>
          Away alerts on any door, window or motion. Night alerts on doors and windows. Home only logs.
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {MODES.map(([id, label]) => <button key={id} style={btn(hub.mode === id)} onClick={() => hub.setSecurityMode(id)}>{label}</button>)}
        </div>
        {!hub.connected && <div style={{ color: C.amber, fontSize: 13, marginTop: 10 }}>Not connected to the hub. Retrying.</div>}
      </div>

      {locks.length > 0 && (
        <div style={card}>
          <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 8 }}>Locks</div>
          {locks.map((d) => (
            <div key={d.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", minHeight: 48 }}>
              <span style={{ color: C.textPrimary }}>{d.name}</span>
              <button style={{ ...btn(!d.state.locked), flex: "none", padding: "0 16px" }} disabled={!d.online}
                onClick={() => hub.command(d.id, "locked", !d.state.locked)}>{d.state.locked ? "Locked. Tap to unlock" : "Unlocked. Tap to lock"}</button>
            </div>
          ))}
        </div>
      )}

      <div style={card}>
        <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 8 }}>Sensors</div>
        {sensors.length === 0 && <div style={{ color: C.textSecondary, fontSize: 13 }}>No sensors yet. Pair them in Zigbee2MQTT, Z-Wave JS UI or a Matter app and they appear here.</div>}
        {sensors.map((d) => {
          const [t, col] = sensorText(d);
          return (
            <div key={d.id} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: `1px solid ${C.border}` }}>
              <span style={{ color: C.textPrimary }}>{d.name} <span style={{ color: C.textDim, fontSize: 12 }}>{d.protocol}</span></span>
              <span style={{ fontFamily: mono, fontSize: 12, color: col }}>{t}{d.state.battery != null ? `  ${Math.round(d.state.battery)}%` : ""}</span>
            </div>
          );
        })}
      </div>

      <div style={card}>
        <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 8 }}>Cameras</div>
        {hub.cameras.length === 0 && <div style={{ color: C.textSecondary, fontSize: 13 }}>Add camera streams to cameras in config.json.</div>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 10 }}>
          {hub.cameras.map((c) => (
            <div key={c.id}>
              <div style={{ color: C.textSecondary, fontSize: 12, marginBottom: 4 }}>{c.name}</div>
              <iframe title={c.name} loading="lazy" allow="autoplay" style={{ width: "100%", aspectRatio: "16 / 9", border: `1px solid ${C.border}`, borderRadius: 6, background: "#000" }}
                src={`${location.protocol}//${location.hostname}:${hub.go2rtcPort}/stream.html?src=${encodeURIComponent(c.id)}&mode=webrtc`} />
            </div>
          ))}
        </div>
      </div>

      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ color: C.textPrimary, fontWeight: 600 }}>Security log</span>
          <button onClick={() => setFilter(filter === "info" ? "alert" : "info")} style={{ ...btn(false), flex: "none", minHeight: 36, padding: "0 12px" }}>
            {filter === "info" ? "Show alerts only" : "Show everything"}
          </button>
        </div>
        {shown.length === 0 && <div style={{ color: C.textSecondary, fontSize: 13 }}>Nothing logged yet.</div>}
        <div style={{ maxHeight: 360, overflowY: "auto" }}>
          {shown.map((e, i) => (
            <div key={`${e.ts}-${i}`} style={{ display: "flex", gap: 10, padding: "6px 0", borderBottom: `1px solid ${C.border}`, fontSize: 13 }}>
              <span style={{ fontFamily: mono, fontSize: 11, color: C.textDim, flexShrink: 0 }}>{new Date(e.ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
              <span style={{ color: SEV[e.severity] || C.textPrimary }}>{e.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
