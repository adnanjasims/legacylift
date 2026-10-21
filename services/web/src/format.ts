import type { JobReport } from "./types.ts";

export function costLabel(report: JobReport): string {
  if (report.usage.length === 0) {
    return "0";
  }
  let total = 0;
  for (const item of report.usage) {
    if (item.estimated_cost === null) {
      return "n/a";
    }
    total += item.estimated_cost;
  }
  return total.toFixed(6);
}

export function tokenLabel(report: JobReport): string {
  let tokensIn = 0;
  let tokensOut = 0;
  for (const item of report.usage) {
    tokensIn += item.tokens_in;
    tokensOut += item.tokens_out;
  }
  return `${tokensIn}/${tokensOut}`;
}
