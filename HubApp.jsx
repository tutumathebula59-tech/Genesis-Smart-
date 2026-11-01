import { useCallback, useEffect, useState } from "react";
import { C, mono } from "./theme";
import {
  HomeIcon, CpuIcon, ChatIcon, TerminalIcon, SettingsIcon,
  SignalIcon, ActivityIcon, UserIcon, LogOutIcon,
} from "./icons";
import { ShieldIcon, BoltIcon, WifiIcon } from "./icons/extra";
import { useHub } from "./hooks/useHub";
import { AlertBanner } from "./components/AlertBanner";
import { SecurityTab } from "./features/security/SecurityTab";
import { EnergyTab } from "./features/energy/EnergyTab";
import { WifiPanel } from "./features/network/WifiPanel";
import { useDevices } from "./hooks/useDevices";
import { useWeather } from "./hooks/useWeather";
import { Dashboard } from "./features/dashboard/Dashboard";
import { DevicesTab } from "./features/devices/DevicesTab";
import { AssistantTab } from "./features/assistant/AssistantTab";
import { TerminalTab } from "./features/terminal/TerminalTab";
import { useTerminalCommands } from "./features/terminal/useTerminalCommands";
import { SettingsTab } from "./features/settings/SettingsTab";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: HomeIcon },
  { id: "devices", label: "Devices", icon: CpuIcon },
  { id: "security", label: "Security", icon: ShieldIcon },
  { id: "energy", label: "Energy", icon: BoltIcon },
  { id: "assistant", label: "Assistant", icon: ChatIcon },
  { id: "terminal", label: "Terminal", icon: TerminalIcon },
  { id: "network", label: "Wi-Fi", icon: WifiIcon },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

export function HubApp({ username, authToken, onLogout }) {
  const [activeTab, setActiveTab] = useState("dashboard");
  const hub = useHub(authToken);
  const { devices, toggleOnline, toggleState, findDevice } = useDevices();
  const [now, setNow] = useState(new Date());
  const [currentSpeed, setCurrentSpeed] = useState(148);
  const [speedHistory, setSpeedHistory] = useState(
    Array.from({ length: 20 }, (_, i) => ({ i, value: 140 + Math.round(Math.random() * 20) }))
  );
  const [settings, setSettings] = useState({ ssid: "HomeHub-5G", wifiPassword: "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022", mqttHost: "mosquitto", mqttPort: "1883", mqttUser: "hub" });
  const [weatherSettings, setWeatherSettings] = useState({ city: "New York", useDeviceLocation: true, unit: "fahrenheit" });
  const { weather, fetchWeather } = useWeather(weatherSettings);

  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t); }, []);
  useEffect(() => {
    const t = setInterval(() => {
      setCurrentSpeed((prev) => {
        const next = Math.max(60, Math.min(300, prev + (Math.random() * 24 - 12)));
        const rounded = Math.round(next);
        setSpeedHistory((h) => [...h.slice(-19), { i: h.length, value: rounded }]);
        return rounded;
      });
    }, 2000);
    return () => clearInterval(t);
  }, []);

  const runCommand = useTerminalCommands({
    devices, ssid: settings.ssid, currentSpeed, toggleOnline, toggleState, findDevice,
    weather, weatherUnit: weatherSettings.unit,
  });

  return (
    <div style={{ width: "100%", minHeight: "100vh", display: "flex", flexDirection: "column", backgroundColor: C.bg }}>
      <AlertBanner alert={hub.alert} onDismiss={hub.dismissAlert} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px",
        paddingTop: "calc(10px + var(--safe-top))", paddingLeft: "calc(16px + var(--safe-left))", paddingRight: "calc(16px + var(--safe-right))",
        borderBottom: `1px solid ${C.border}`, backgroundColor: C.panel, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 8, height: 8, borderRadius: 9999, backgroundColor: C.green }} />
          <span style={{ fontSize: 14, fontWeight: 600, color: C.textPrimary }}>Genesis Smart Home</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: mono, fontSize: 11, color: C.textSecondary }}>
            <SignalIcon size={13} color={C.cyan} />{currentSpeed} Mbps
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: mono, fontSize: 11, color: C.textSecondary }}>
            <ActivityIcon size={13} color={hub.connected ? C.green : C.red} />{hub.connected ? "Online" : "Hub offline"}
          </div>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.textDim }}>
            {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
          <div style={{ width: 1, alignSelf: "stretch", backgroundColor: C.border }} />
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontFamily: mono, fontSize: 11, color: C.textSecondary }}>
            <UserIcon size={13} color={C.textDim} />{username}
          </div>
          <button onClick={onLogout} title="Log out" className="tap-target" style={{ display: "flex", alignItems: "center", justifyContent: "center",
            background: "transparent", border: "none", color: C.textDim, padding: 2 }}>
            <LogOutIcon size={16} />
          </button>
        </div>
      </div>
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <div style={{ display: "flex", flexDirection: "column", flexShrink: 0, width: 64, overflowY: "auto", borderRight: `1px solid ${C.border}`, backgroundColor: C.panel,
          paddingLeft: "var(--safe-left)", paddingBottom: "var(--safe-bottom)" }}>
          <nav style={{ display: "flex", flexDirection: "column", gap: 6, padding: 8 }}>
            {NAV.map((item) => {
              const active = activeTab === item.id, NIcon = item.icon;
              return (
                <button key={item.id} onClick={() => setActiveTab(item.id)} title={item.label} className="tap-target" style={{
                  display: "flex", alignItems: "center", justifyContent: "center", padding: "10px",
                  borderRadius: 6, border: "none", backgroundColor: active ? C.panelRaised : "transparent" }}>
                  <NIcon size={19} color={active ? C.cyan : C.textSecondary} />
                </button>
              );
            })}
          </nav>
        </div>
        <div style={{ flex: 1, minWidth: 0, overflowY: "auto", padding: 16,
          paddingRight: "calc(16px + var(--safe-right))", paddingBottom: "calc(16px + var(--safe-bottom))" }}>
          <h1 style={{ fontSize: 17, fontWeight: 600, color: C.textPrimary, margin: "0 0 16px 0" }}>
            {NAV.find((n) => n.id === activeTab)?.label}
          </h1>
          {activeTab === "dashboard" && <Dashboard devices={devices} speedHistory={speedHistory} currentSpeed={currentSpeed} ssid={settings.ssid} weather={weather} onWeatherRefresh={fetchWeather} />}
          {activeTab === "devices" && <DevicesTab devices={devices} toggleOnline={toggleOnline} toggleState={toggleState} />}
          {activeTab === "security" && <SecurityTab hub={hub} />}
          {activeTab === "energy" && <EnergyTab hub={hub} />}
          {activeTab === "network" && <WifiPanel authToken={authToken} />}
          {activeTab === "assistant" && <AssistantTab devices={devices} toggleOnline={toggleOnline} toggleState={toggleState} findDevice={findDevice} authToken={authToken} />}
          {activeTab === "terminal" && <TerminalTab runCommand={runCommand} />}
          {activeTab === "settings" && <SettingsTab settings={settings} setSettings={setSettings} weatherSettings={weatherSettings} setWeatherSettings={setWeatherSettings} onWeatherRefresh={fetchWeather} />}
        </div>
      </div>
    </div>
  );
}
