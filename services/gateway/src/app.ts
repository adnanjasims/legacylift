import fastifyJwt from "@fastify/jwt";
import Fastify, { type FastifyInstance } from "fastify";

import { healthPayload } from "./health.js";

export type GatewayOptions = {
  jwtSecret?: string;
  orchestratorUrl?: string;
  fetchImpl?: typeof fetch;
};

/**
 * Build the Fastify app with liveness, login, and job proxy routes.
 * Tests call inject() on the returned instance. Production calls listen()
 * from index.ts.
 */
export async function buildApp(options: GatewayOptions = {}): Promise<FastifyInstance> {
  const jwtSecret = (options.jwtSecret ?? process.env.JWT_SECRET ?? "").trim();
  const orchestratorUrl = (
    options.orchestratorUrl ??
    process.env.ORCHESTRATOR_URL ??
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");
  const fetchImpl = options.fetchImpl ?? fetch;

  const app = Fastify({
    logger: {
      level: process.env.LOG_LEVEL ?? "info",
    },
  });

  await app.register(fastifyJwt, {
    secret: jwtSecret || "unconfigured",
  });

  app.get("/health", async () => healthPayload());
  app.get("/ready", async () => healthPayload());

  app.post("/login", async (request, reply) => {
    if (!jwtSecret) {
      return reply.code(503).send({ error: "JWT_SECRET is not set" });
    }
    const response = await fetchImpl(`${orchestratorUrl}/auth/login`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request.body ?? {}),
    });
    const payload = (await response.json()) as Record<string, unknown>;
    return reply.code(response.status).send(payload);
  });

  app.addHook("onRequest", async (request, reply) => {
    const path = request.url.split("?")[0];
    if (path === "/health" || path === "/ready" || path === "/login") {
      return;
    }
    try {
      await request.jwtVerify();
    } catch {
      return reply.code(401).send({ error: "unauthorized" });
    }
  });

  app.post("/jobs", async (request, reply) => {
    const response = await fetchImpl(`${orchestratorUrl}/jobs`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: request.headers.authorization ?? "",
      },
      body: JSON.stringify(request.body ?? {}),
    });
    const payload = (await response.json()) as Record<string, unknown>;
    return reply.code(response.status).send(payload);
  });

  app.get("/jobs/:id", async (request, reply) => {
    const params = request.params as { id: string };
    const response = await fetchImpl(`${orchestratorUrl}/jobs/${params.id}`, {
      method: "GET",
      headers: {
        authorization: request.headers.authorization ?? "",
      },
    });
    const payload = (await response.json()) as Record<string, unknown>;
    return reply.code(response.status).send(payload);
  });

  return app;
}
