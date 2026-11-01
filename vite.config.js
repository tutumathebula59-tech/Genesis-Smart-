import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icons/icon-192.png", "icons/icon-512.png"],
      manifest: {
        name: "Genesis Smart Home",
        short_name: "Genesis",
        description: "Dashboard, device manager, and terminal for your home IoT hub",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "portrait-primary",
        background_color: "#12161b",
        theme_color: "#12161b",
        icons: [
          { src: "icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any maskable" },
          { src: "icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
      workbox: {
        // Cache the app shell; API calls (/auth, /assistant, /devices) always hit the network.
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
        navigateFallbackDenylist: [/^\/auth/, /^\/assistant/, /^\/devices/, /^\/hub/],
      },
      devOptions: { enabled: false },
    }),
  ],
  server: {
    // Proxy API calls to the FastAPI hub during local dev so the frontend
    // can just call relative paths like `/auth/login` in both dev and prod.
    proxy: {
      "/auth": "http://localhost:8000",
      "/assistant": "http://localhost:8000",
      "/devices": "http://localhost:8000",
      "/hub": { target: "http://localhost:8000", ws: true },
    },
  },
});
