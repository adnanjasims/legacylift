import Fastify, { type FastifyInstance } from "fastify";

import { healthPayload } from "./health.js";

/**
 * Build the Fastify app with liveness and readiness routes.
 * Tests call inject() on the returned instance. Production calls listen()
 * from index.ts.
 */
export function buildApp(): FastifyInstance {
  const app = Fastify({
    logger: {
      level: process.env.LOG_LEVEL ?? "info",
    },
  });

  app.get("/health", async () => healthPayload());
  app.get("/ready", async () => healthPayload());

  return app;
}
