import { expect, test } from "vitest";

import { buildApp } from "../src/app.js";
import { healthPayload } from "../src/health.js";

test("GET /health returns ok", async () => {
  const app = await buildApp();
  try {
    const response = await app.inject({ method: "GET", url: "/health" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual(healthPayload());
  } finally {
    await app.close();
  }
});

test("GET /ready returns ok", async () => {
  const app = await buildApp();
  try {
    const response = await app.inject({ method: "GET", url: "/ready" });
    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual(healthPayload());
  } finally {
    await app.close();
  }
});
