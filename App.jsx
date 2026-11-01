import { useState } from "react";
import { useDisconnect } from "wagmi";
import { AuthGate } from "./features/auth/AuthGate";
import { HubApp } from "./HubApp";

export default function App() {
  const { disconnect } = useDisconnect();
  const [auth, setAuth] = useState(() => {
    try {
      const token = localStorage.getItem("genesis_auth_token");
      const username = localStorage.getItem("genesis_auth_user");
      return token ? { status: "authed", token, username } : { status: "guest" };
    } catch (e) {
      return { status: "guest" };
    }
  });

  const handleLogin = (token, username, address) => {
    try {
      localStorage.setItem("genesis_auth_token", token);
      localStorage.setItem("genesis_auth_user", username);
      if (address) localStorage.setItem("genesis_auth_address", address);
    } catch (e) {}
    setAuth({ status: "authed", token, username });
  };

  const handleLogout = () => {
    try {
      localStorage.removeItem("genesis_auth_token");
      localStorage.removeItem("genesis_auth_user");
      localStorage.removeItem("genesis_auth_address");
    } catch (e) {}
    disconnect();
    setAuth({ status: "guest" });
  };

  if (auth.status !== "authed") return <AuthGate onLogin={handleLogin} />;
  return <HubApp username={auth.username} authToken={auth.token} onLogout={handleLogout} />;
}
