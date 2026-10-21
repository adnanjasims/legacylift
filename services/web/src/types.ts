export type JobStatus = "queued" | "running" | "completed" | "failed" | "dead_lettered";

export type JobInfo = {
  id: string;
  source: string;
  status: JobStatus;
  attempt: number;
  error: string | null;
  report_dir: string | null;
};

export type FileReport = {
  path: string;
  status: string;
  tests_before_passed: number;
  tests_before_failed: number;
  tests_after_passed: number;
  tests_after_failed: number;
  compile_ok: boolean;
  diff: string;
  after_failures: string[];
  attempts: number;
  llm_used: boolean;
};

export type UsageEntry = {
  provider: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
  estimated_cost: number | null;
  attempt: number;
};

export type JobReport = {
  job_id: string;
  source: string;
  mode: string;
  provider: string | null;
  model_id: string | null;
  files: FileReport[];
  notes: string[];
  wall_clock_sec: number;
  usage: UsageEntry[];
};
