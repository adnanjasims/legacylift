import fastifyJwt from "@fastify/jwt";
import multipart from "@fastify/multipart";
import Fastify, { type FastifyInstance, type FastifyReply } from "fastify";

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
  await app.register(multipart, {
    limits: { fileSize: 10 * 1024 * 1024 },
  });

  app.get("/health", async () => healthPayload());
  app.get("/ready", async () => healthPayload());

  app.post("/login", async (request, reply) => {
    if (!jwtSecret) {
      return reply.code(503).send({ error: "JWT_SECRET is not set" });
    }
    return proxyJson(
      fetchImpl,
      `${orchestratorUrl}/auth/login`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request.body ?? {}),
      },
      reply,
    );
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
    return proxyJson(
      fetchImpl,
      `${orchestratorUrl}/jobs`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: request.headers.authorization ?? "",
        },
        body: JSON.stringify(request.body ?? {}),
      },
      reply,
    );
  });

  app.post("/jobs/upload", async (request, reply) => {
    const uploaded = await request.file();
    if (uploaded === undefined) {
      return reply.code(400).send({ error: "zip file is required" });
    }
    const buf = await uploaded.toBuffer();
    const form = new FormData();
    form.append("file", new Blob([new Uint8Array(buf)]), uploaded.filename);
    const response = await fetchImpl(`${orchestratorUrl}/jobs/upload`, {
      method: "POST",
      headers: { authorization: request.headers.authorization ?? "" },
      body: form,
    });
    const payload = (await response.json()) as Record<string, unknown>;
    return reply.code(response.status).send(payload);
  });

  app.get("/jobs/:id", async (request, reply) => {
    const params = request.params as { id: string };
    return proxyJson(
      fetchImpl,
      `${orchestratorUrl}/jobs/${params.id}`,
      {
        method: "GET",
        headers: { authorization: request.headers.authorization ?? "" },
      },
      reply,
    );
  });

  app.get("/jobs/:id/report", async (request, reply) => {
    const params = request.params as { id: string };
    return proxyJson(
      fetchImpl,
      `${orchestratorUrl}/jobs/${params.id}/report`,
      {
        method: "GET",
        headers: { authorization: request.headers.authorization ?? "" },
      },
      reply,
    );
  });

  app.get("/jobs/:id/events", async (request, reply) => {
    const params = request.params as { id: string };
    const response = await fetchImpl(`${orchestratorUrl}/jobs/${params.id}/events`, {
      method: "GET",
      headers: { authorization: request.headers.authorization ?? "" },
    });
    reply.hijack();
    reply.raw.writeHead(response.status, {
      "content-type": response.headers.get("content-type") ?? "text/event-stream",
      "cache-control": "no-cache",
    });
    if (response.body === null) {
      reply.raw.end();
      return;
    }
    const reader = response.body.getReader();
    try {
      for (;;) {
        const step = await reader.read();
        if (step.done) {
          break;
        }
        reply.raw.write(step.value);
      }
    } finally {
      reply.raw.end();
    }
  });

  return app;
}

async function proxyJson(
  fetchImpl: typeof fetch,
  url: string,
  init: RequestInit,
  reply: FastifyReply,
): Promise<unknown> {
  const response = await fetchImpl(url, init);
  const payload = (await response.json()) as Record<string, unknown>;
  return reply.code(response.status).send(payload);
}
