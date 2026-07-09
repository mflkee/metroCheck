import path from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

const srcPath = fileURLToPath(new URL("./src", import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBaseUrl = process.env.VITE_API_BASE_URL ?? env.VITE_API_BASE_URL ?? "/api/v1";
  const apiProxyTarget =
    process.env.VITE_API_PROXY_TARGET ?? env.VITE_API_PROXY_TARGET ?? "http://localhost:8002";
  const frontendPort = Number(process.env.FRONTEND_PORT ?? env.FRONTEND_PORT ?? "5173");

  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) {
              return undefined;
            }
            return "vendor";
          },
        },
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(srcPath),
      },
    },
    server: {
      host: "0.0.0.0",
      port: frontendPort,
      proxy: apiBaseUrl.startsWith("/")
        ? {
            "/api": {
              target: apiProxyTarget,
              changeOrigin: true,
            },
          }
        : undefined,
    },
  };
});
