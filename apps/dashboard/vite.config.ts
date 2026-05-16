import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const apiTarget = process.env.VITE_ORIGENLAB_API_BASE_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/health": { target: apiTarget, changeOrigin: true },
      "/dashboard": { target: apiTarget, changeOrigin: true },
      "/contacts": { target: apiTarget, changeOrigin: true },
      "/organizations": { target: apiTarget, changeOrigin: true },
      "/outbound": { target: apiTarget, changeOrigin: true },
      "/meta": { target: apiTarget, changeOrigin: true },
      "/classification": { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
