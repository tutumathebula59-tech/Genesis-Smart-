// Desktop shell (Windows .exe/.msi, macOS .dmg, Linux .deb). It opens your hub, which serves the app,
// so it works offline on your home network. Set the hub address with GENESIS_HUB_URL or hub.json in the app's data folder.
import { app, BrowserWindow } from "electron";
import fs from "node:fs";
import path from "node:path";

function hubUrl() {
  if (process.env.GENESIS_HUB_URL) return process.env.GENESIS_HUB_URL;
  try { return JSON.parse(fs.readFileSync(path.join(app.getPath("userData"), "hub.json"), "utf8")).url; } catch { return "http://genesis.local:8000"; }
}

function create() {
  const kiosk = process.argv.includes("--kiosk");
  const win = new BrowserWindow({ width: 1100, height: 760, backgroundColor: "#12161b", kiosk, autoHideMenuBar: true, title: "Genesis Smart Home" });
  const url = hubUrl();
  const retry = () => setTimeout(() => !win.isDestroyed() && win.loadURL(url), 5000);
  win.webContents.on("did-fail-load", (_e, code, _d, _u, isMain) => {
    if (!isMain || code === -3) return;
    win.loadURL("data:text/html," + encodeURIComponent(
      `<body style="background:#12161b;color:#e7ebee;font-family:sans-serif;padding:40px"><h2>Can't reach the hub</h2><p>Looking for ${url}. Retrying every 5 seconds.</p></body>`));
    retry();
  });
  win.loadURL(url);
}

app.whenReady().then(create);
app.on("window-all-closed", () => app.quit());
