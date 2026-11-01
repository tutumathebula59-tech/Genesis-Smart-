#!/bin/bash
# genesis-kiosk.sh
# Waits for the Genesis Smart Home backend to respond, then opens it
# full-screen (kiosk mode). Runs automatically at login via the GNOME
# autostart entry (genesis-kiosk.desktop).

# --- Configure this -----------------------------------------------------
URL="http://localhost:8000"
# -------------------------------------------------------------------------

# Give GNOME a moment to finish starting up.
sleep 5

# Disable screen blanking / power saving so the kiosk screen stays on.
gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null
xset s off -dpms 2>/dev/null

# Wait (up to ~2 minutes) for the backend to actually be up before
# opening the browser, so you don't land on a connection-refused page.
for i in $(seq 1 60); do
  if curl -sf -o /dev/null "$URL"; then
    break
  fi
  sleep 2
done

# Launch the browser in kiosk (full-screen, no chrome) mode.
if command -v firefox >/dev/null 2>&1; then
  exec firefox --kiosk "$URL"
elif command -v chromium-browser >/dev/null 2>&1; then
  exec chromium-browser --kiosk --noerrdialogs --disable-infobars --incognito "$URL"
elif command -v chromium >/dev/null 2>&1; then
  exec chromium --kiosk --noerrdialogs --disable-infobars --incognito "$URL"
else
  notify-send "Genesis Kiosk" "No browser found. Install firefox or chromium." 2>/dev/null
  exit 1
fi
