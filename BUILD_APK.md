# Build the Android APK

Needs: Node 20, JDK 17, Android SDK (Android Studio installs it).

    npm install
    npm run apk

Output: android/app/build/outputs/apk/debug/app-debug.apk
Copy it to the phone and install (allow "install unknown apps").

No local setup? Push this folder to GitHub, open Actions > "Build APK",
and download the "genesis-smart-home-apk" artifact.

Hub address: edit "server.url" in capacitor.config.json to your hub's
LAN address (e.g. http://192.168.1.20:8000), then run `npx cap sync android`.
The app loads from the hub, so it works fully offline on your home network.

Play Store release needs a signed release build (assembleRelease + keystore).
