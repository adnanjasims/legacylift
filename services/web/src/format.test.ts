import { expect, test } from "vitest";

import { costLabel, tokenLabel } from "./format.ts";
import type { JobReport } from "./types.ts";

function report(usage: JobReport["usage"]): JobReport {
  return {
    job_id: "j1",
    source: "corpus/x",
    mode: "deterministic",
    provider: null,
    model_id: null,
    files: [],
    notes: [],
    wall_clock_sec: 1,
    usage,
  };
}

test("costLabel is n/a when a usage row has no rate", () => {
  expect(
    costLabel(
      report([
        {
          provider: "local",
          model: "x",
          tokens_in: 2,
          tokens_out: 1,
          latency_ms: 1,
          estimated_cost: null,
          attempt: 1,
        },
      ]),
    ),
  ).toBe("n/a");
});

test("tokenLabel sums in and out", () => {
  expect(
    tokenLabel(
      report([
        {
          provider: "local",
          model: "x",
          tokens_in: 10,
          tokens_out: 3,
          latency_ms: 1,
          estimated_cost: 0,
          attempt: 1,
        },
        {
          provider: "local",
          model: "x",
          tokens_in: 2,
          tokens_out: 4,
          latency_ms: 1,
          estimated_cost: 0,
          attempt: 2,
        },
      ]),
    ),
  ).toBe("12/7");
});
