import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const apiTarget = process.env.VITE_API_TARGET ?? "http://127.0.0.1:8765";

const apiProxyPaths = ["/health", "/config", "/works", "/overview", "/events"];

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      apiProxyPaths.map((path) => [
        path,
        { target: apiTarget, changeOrigin: true },
      ]),
    ),
  },
  test: {
    environment: "jsdom",
  },
});
