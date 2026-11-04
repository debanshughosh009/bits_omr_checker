import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// `npm run dev` proxies the API to app/server.py, so start that too
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { chunkSizeWarningLimit: 1500 }, // one local bundle; splitting buys nothing here
  server: { proxy: { "/api": "http://127.0.0.1:8765", "/data": "http://127.0.0.1:8765", "/scans_to_csv": "http://127.0.0.1:8765" } },
});
