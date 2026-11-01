import { useEffect } from "react";
import { C } from "../theme";

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator(); o.frequency.value = 880; o.connect(ctx.destination);
    o.start(); o.stop(ctx.currentTime + 0.6);
  } catch (e) { /* audio needs a prior tap on some browsers */ }
}

export function AlertBanner({ alert, onDismiss }) {
  useEffect(() => { if (alert) beep(); }, [alert]);
  if (!alert) return null;
  const critical = alert.severity === "critical";
  return (
    <div role="alert" style={{ position: "fixed", left: 0, right: 0, top: 0, zIndex: 50, display: "flex", alignItems: "center", gap: 12,
      padding: "12px 16px", paddingTop: "calc(12px + var(--safe-top))", backgroundColor: critical ? C.red : C.amber, color: "#12161b", fontWeight: 600 }}>
      <span style={{ flex: 1 }}>{alert.message}</span>
      <button onClick={onDismiss} className="tap-target" style={{ border: "1px solid #12161b", background: "transparent", color: "#12161b", borderRadius: 6, padding: "0 14px", fontWeight: 600 }}>Dismiss</button>
    </div>
  );
}
