import { expect, test } from "vitest";

import { buildApp } from "../src/app.js";

test("GET /jobs without a token is unauthorized", async () => {
  const app = await buildApp({ jwtSecret: "unit-test-secret" });
  try {
    const response = await app.inject({ method: "GET", url: "/jobs/abc" });
    expect(response.statusCode).toBe(401);
  } finally {
    await app.close();
  }
});

test("POST /login without JWT_SECRET returns 503", async () => {
  const app = await buildApp({ jwtSecret: "" });
  try {
    const response = await app.inject({
      method: "POST",
      url: "/login",
      payload: { username: "alice", password: "dev-alice" },
    });
    expect(response.statusCode).toBe(503);
  } finally {
    await app.close();
  }
});
