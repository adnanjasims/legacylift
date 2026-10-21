import { expect, test } from "vitest";

import { healthPayload } from "./health.ts";

test("health payload names the web service", () => {
  expect(healthPayload()).toEqual({ status: "ok", service: "web" });
});
