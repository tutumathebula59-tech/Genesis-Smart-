# Auto-open Genesis Smart Home on boot (CentOS + GNOME, auto-login)

This makes the browser open your hub full-screen right after the machine
boots and logs in — no manual steps needed at the physical screen.

## 1. Install a browser (if not already present)

Firefox is in CentOS's default repos and is the most reliable kiosk browser
here — Chromium isn't shipped by CentOS/RHEL directly.

```bash
sudo dnf install -y firefox
```
(If you'd rather use Chromium, install it via Flatpak: `sudo dnf install -y flatpak && flatpak install -y flathub org.chromium.Chromium`, then edit `genesis-kiosk.sh` to launch `flatpak run org.chromium.Chromium` instead.)

## 2. Install the kiosk script

```bash
sudo cp genesis-kiosk.sh /usr/local/bin/genesis-kiosk.sh
sudo chmod +x /usr/local/bin/genesis-kiosk.sh
```

Open `/usr/local/bin/genesis-kiosk.sh` and set `URL` at the top to wherever
your hub is actually served from (e.g. `http://localhost:8000` if the
FastAPI backend serves the PWA directly, or a Cloudflare tunnel URL).

## 3. Install the autostart entry

This runs the script automatically once GNOME logs in (which your machine
is already set to do on boot):

```bash
mkdir -p ~/.config/autostart
cp genesis-kiosk.desktop ~/.config/autostart/
```

## 4. Reboot and test

```bash
sudo reboot
```

The machine should boot, auto-login to GNOME, wait for the backend to
respond, then open the hub full-screen with no browser toolbar.

## Getting out of kiosk mode (for maintenance)

- Firefox kiosk mode: `Alt+F4` closes it, or SSH in and `pkill firefox`.
- To temporarily disable the autostart: `mv ~/.config/autostart/genesis-kiosk.desktop ~/.config/autostart/genesis-kiosk.desktop.disabled`, then reboot.

## Notes

- If the backend isn't running as a systemd service yet, kiosk mode will
  just retry for ~2 minutes then give up with a browser error page — worth
  also setting up your FastAPI hub as a `systemd` service (`systemctl enable`)
  so it starts before/alongside the desktop session. Ask if you want that
  service file too.
- To hide the mouse cursor when idle: `sudo dnf install -y unclutter` and
  add `unclutter -idle 2 &` near the top of `genesis-kiosk.sh`.
