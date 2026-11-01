import { useEffect, useState } from "react";
import { C, mono } from "../../theme";
import { saveBlob } from "../../hooks/useHub";

const card = { backgroundColor: C.panel, border: `1px solid ${C.border}`, borderRadius: 8, padding: 14, marginBottom: 14 };
const btn = (primary) => ({ minHeight: 44, padding: "0 14px", borderRadius: 6, border: `1px solid ${primary ? C.cyan : C.borderLight}`, background: primary ? C.cyan : "transparent", color: primary ? C.bg : C.textPrimary, fontWeight: 600 });
const input = { minHeight: 44, padding: "0 10px", borderRadius: 6, border: `1px solid ${C.borderLight}`, background: C.bg, color: C.textPrimary };
const kw = (w) => (w == null ? "-" : Math.abs(w) >= 1000 ? `${(w / 1000).toFixed(2)} kW` : `${Math.round(w)} W`);
const Title = ({ children }) => <div style={{ color: C.textPrimary, fontWeight: 600, marginBottom: 8 }}>{children}</div>;

export function EnergyTab({ hub }) {
  const s = hub.site;
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [report, setReport] = useState(null);
  const [backups, setBackups] = useState([]);
  const [slot, setSlot] = useState({ start: "", end: "" });
  const [msg, setMsg] = useState("");
  const say = (e) => setMsg(e.message || String(e));

  useEffect(() => { hub.api(`/energy/report?month=${month}`).then(setReport).catch(say); }, [month]); // eslint-disable-line
  const loadBackups = () => hub.api("/backups").then(setBackups).catch(say);
  useEffect(() => { loadBackups(); }, []); // eslint-disable-line

  const plugs = hub.devices.filter((d) => d.kind === "plug" || d.kind === "switch");
  const climate = hub.devices.filter((d) => d.kind === "thermostat");
  const tiles = [["Solar", kw(s.solar_w), C.amber], ["Home load", kw(s.load_w), C.cyan], ["Grid", s.grid_ok === false ? "Down" : kw(s.grid_w), s.grid_ok === false ? C.red : C.green],
    ["Battery", s.battery_soc != null ? `${Math.round(s.battery_soc)}%` : "-", C.green]];

  const addSlot = async () => {
    try {
      const cur = (await hub.api("/loadshedding")).slots;
      await hub.api("/loadshedding", { method: "PUT", body: JSON.stringify([...cur, { start: `${slot.start}:00`, end: `${slot.end}:00`, stage: "" }]) });
      setSlot({ start: "", end: "" }); setMsg("Slot added"); hub.reload();
    } catch (e) { say(e); }
  };

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 10, marginBottom: 14 }}>
        {tiles.map(([label, v, col]) => (
          <div key={label} style={{ ...card, marginBottom: 0 }}>
            <div style={{ color: C.textSecondary, fontSize: 12 }}>{label}</div>
            <div style={{ fontFamily: mono, fontSize: 20, color: col, marginTop: 4 }}>{v}</div>
          </div>
        ))}
      </div>

      <div style={card}>
        <Title>Load shedding {hub.ls.active && <span style={{ color: C.amber, fontSize: 13 }}>(active: non-essential loads are off)</span>}</Title>
        {hub.ls.slots.length === 0 && <div style={{ color: C.textSecondary, fontSize: 13, marginBottom: 8 }}>No upcoming slots. Add them below. The schedule is stored on the hub and works offline.</div>}
        {hub.ls.slots.map((x) => <div key={x.start} style={{ fontFamily: mono, fontSize: 12, color: C.textSecondary }}>{x.start.replace("T", " ").slice(0, 16)} to {x.end.slice(11, 16)}</div>)}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          <input style={input} type="datetime-local" value={slot.start} onChange={(e) => setSlot({ ...slot, start: e.target.value })} aria-label="Start" />
          <input style={input} type="datetime-local" value={slot.end} onChange={(e) => setSlot({ ...slot, end: e.target.value })} aria-label="End" />
          <button style={btn(true)} disabled={!slot.start || !slot.end} onClick={addSlot}>Add slot</button>
        </div>
      </div>

      {climate.length > 0 && (
        <div style={card}>
          <Title>Heating and cooling</Title>
          {climate.map((d) => (
            <div key={d.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", minHeight: 52 }}>
              <span style={{ color: C.textPrimary }}>{d.name}<br /><span style={{ fontFamily: mono, fontSize: 12, color: C.textSecondary }}>{d.state.temperature ?? "-"}° now, mode {d.state.mode || "-"}</span></span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button style={btn(false)} aria-label="Lower" onClick={() => hub.command(d.id, "setpoint", (d.state.setpoint ?? 21) - 0.5)}>-</button>
                <span style={{ fontFamily: mono, minWidth: 48, textAlign: "center", color: C.cyan }}>{d.state.setpoint ?? "-"}°</span>
                <button style={btn(false)} aria-label="Raise" onClick={() => hub.command(d.id, "setpoint", (d.state.setpoint ?? 21) + 0.5)}>+</button>
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={card}>
        <Title>Plugs and appliances</Title>
        {plugs.length === 0 && <div style={{ color: C.textSecondary, fontSize: 13 }}>No smart plugs found yet.</div>}
        {plugs.map((d) => (
          <div key={d.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", minHeight: 48 }}>
            <span style={{ color: d.online ? C.textPrimary : C.textDim }}>{d.name}<span style={{ fontFamily: mono, fontSize: 12, color: C.textSecondary }}>  {d.state.power_w != null ? kw(d.state.power_w) : ""}</span></span>
            <button style={btn(!!d.state.on)} disabled={!d.online} onClick={() => hub.command(d.id, "on", !d.state.on)}>{d.state.on ? "On" : "Off"}</button>
          </div>
        ))}
      </div>

      <div style={card}>
        <Title>Monthly report</Title>
        <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
          <input style={input} type="month" value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Month" />
          <button style={btn(false)} onClick={() => hub.api(`/energy/report.csv?month=${month}`).then((b) => saveBlob(b, `energy-${month}.csv`)).catch(say)}>Download CSV</button>
        </div>
        {report && (
          <div style={{ fontFamily: mono, fontSize: 12, color: C.textSecondary, lineHeight: 1.8 }}>
            Solar {report.solar_kwh} kWh<br />Home use {report.load_kwh} kWh<br />
            From grid {report.grid_import_kwh} kWh ({report.currency}{report.grid_cost})<br />
            To grid {report.grid_export_kwh} kWh<br />Solar saved about {report.currency}{report.solar_savings}
            {report.devices.slice(0, 8).map((d) => <div key={d.id}>{d.name}: {d.kwh} kWh</div>)}
          </div>
        )}
      </div>

      <div style={card}>
        <Title>Backups</Title>
        <button style={btn(true)} onClick={() => hub.api("/backup", { method: "POST" }).then(() => { setMsg("Backup saved"); loadBackups(); }).catch(say)}>Back up now</button>
        <div style={{ color: C.textSecondary, fontSize: 13, margin: "8px 0" }}>Runs nightly on its own. Set a USB path in config.json to copy each backup to a drive.</div>
        {backups.slice(0, 5).map((b) => (
          <div key={b.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontFamily: mono, fontSize: 12, color: C.textSecondary, minHeight: 40 }}>
            <span>{new Date(b.ts * 1000).toLocaleString()}</span>
            <button style={{ ...btn(false), minHeight: 36 }} onClick={() => hub.api(`/backups/${b.name}`).then((x) => saveBlob(x, b.name)).catch(say)}>Download</button>
          </div>
        ))}
      </div>
      {msg && <div style={{ color: C.amber, fontSize: 13 }}>{msg}</div>}
    </div>
  );
}
