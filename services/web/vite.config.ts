import type { IncomingMessage, ServerResponse } from "node:http";

import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

import { healthPayload } from "./src/health.ts";

const gateway = process.env.GATEWAY_URL ?? "http://127.0.0.1:3000";

const apiProxy = {
  "/api": {
    target: gateway,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

function isHealthPath(url: string | undefined): boolean {
  if (url === undefined) {
    return false;
  }
  const path = url.split("?")[0];
  return path === "/health" || path === "/ready";
}

function handleHealth(
  req: IncomingMessage,
  res: ServerResponse,
  next: () => void,
): void {
  if (!isHealthPath(req.url)) {
    next();
    return;
  }
  res.statusCode = 200;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(healthPayload()));
}

function healthPlugin(): Plugin {
  return {
    name: "legacylift-health",
    configureServer(server) {
      server.middlewares.use(handleHealth);
    },
    configurePreviewServer(server) {
      server.middlewares.use(handleHealth);
    },
  };
}

export default defineConfig({
  plugins: [healthPlugin(), react()],
  server: {
    proxy: apiProxy,
  },
  preview: {
    host: "0.0.0.0",
    port: 5173,
    proxy: apiProxy,
  },
});
