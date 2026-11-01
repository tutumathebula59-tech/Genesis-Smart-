# Genesis Smart Home v3

Local-first smart home hub. Works with no internet. Runs on a Raspberry Pi, mini PC or CentOS box.

**Devices:** Zigbee, Z-Wave and Matter (door, window, motion, smoke and leak sensors, smart locks, plugs, lights, thermostats)
**Security:** alarm modes, instant alerts (app, touchpad, phone push), searchable security log, CCTV live view
**Energy:** solar, battery and grid, per-device use, monthly report (CSV), load shedding automation
**Network:** join Wi-Fi from the app, hotspot for devices, setup hotspot if the network drops
**Safety:** nightly local backups (optional USB copy)

## What this repo contains (and what it doesn't)

This is an upgrade of your existing app. It contains every new or changed file. Copy your existing
`src/features/{auth,dashboard,devices,assistant,terminal,settings}`, `src/icons/index.*`, `src/hooks/useDevices.js`,
`src/hooks/useWeather.js`, `src/lib/*` and `public/icons/*` into the same paths. I didn't have those files.
Nothing here has been run on real hardware or built in CI yet. Expect to fix small things on the first run.

## 1. Hub (server)

    sudo dnf install -y python3 mosquitto NetworkManager
    sudo mkdir -p /opt/genesis && sudo cp -r backend/* /opt/genesis/ && cd /opt/genesis
    python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
    sudo cp genesis.env.example /etc/genesis.env     # set JWT_SECRET (the hub refuses to start without it)
    cp config.example.json /var/lib/genesis/config.json   # edit MQTT, cameras, energy topics
    sudo cp genesis-hub.service /etc/systemd/system/ && sudo systemctl enable --now genesis-hub

Build the frontend (`npm install && npm run build`) and copy `dist/` to `/opt/genesis/dist`. The hub then serves the app at `http://<hub>:8000`.

Companion services (all local):

| Need | Run | Then |
|---|---|---|
| Zigbee | Zigbee2MQTT + a USB coordinator | same MQTT broker |
| Z-Wave | Z-Wave JS UI + a USB stick | enable MQTT gateway with named topics; extend `ZWAVE_MAP` in `hub_core.py` to match what you see |
| Matter | python-matter-server | `matter.url` in config |
| Cameras | go2rtc (`go2rtc -config data/go2rtc.yaml`, generated for you) | add RTSP URLs under `cameras` |
| Phone push | ntfy (self-hosted) | install the ntfy app, subscribe to `alerts.ntfy_topic` |
| Inverter | any bridge that publishes MQTT | map topics under `energy.topics` |

## 2. Apps

| Format | How | Notes |
|---|---|---|
| `.apk` | Actions > Build APK, or `npm run apk` | debug build installs directly |
| `.exe` `.msi` `.dmg` `.deb` | Actions > Build desktop apps | unsigned; add signing secrets to distribute |
| `.ipa` | Actions > Build iOS | unsigned; needs sideloading or an Apple developer account to install |

All apps are thin shells that open your hub. Set `server.url` in `capacitor.config.json` and `GENESIS_HUB_URL` (desktop) to your hub address first.
Before building, set `author.email` and `homepage` in `package.json` (the .deb build needs a real email).

## 3. Wall touchpad

copy `kiosk/genesis-kiosk.sh` to `/usr/local/bin/` and follow `docs/KIOSK_SETUP.md`. Alerts show as a full-width banner with a tone.

## Known limits

- Matter: thermostats are read-only and lights aren't mapped yet.
- Z-Wave topic names vary with gateway settings, so check `ZWAVE_MAP` first if a device doesn't show up.
- Entry/exit delay isn't implemented. Away mode alerts immediately.
- Wi-Fi: most adapters can't be a client and a hotspot at once; use Ethernet or a second adapter.
- Remote access away from home needs a VPN or tunnel; the hub does not open itself to the internet.
- Wallet login: set `WALLET_ALLOWLIST` in `auth_backend.py` before using the hub on any shared network.
