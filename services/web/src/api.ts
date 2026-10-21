import type { JobInfo, JobReport } from "./types.ts";

const API = "/api";

export type LoginResult = {
  token: string;
  username: string;
  role: string;
};

async function readError(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as {
    error?: string;
    detail?: string;
  } | null;
  return body?.error ?? body?.detail ?? `request failed (${response.status})`;
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const response = await fetch(`${API}/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as LoginResult;
}

export async function createJob(token: string, source: string): Promise<JobInfo> {
  const response = await fetch(`${API}/jobs`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ source }),
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as JobInfo;
}

export async function uploadJob(token: string, file: File): Promise<JobInfo> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(`${API}/jobs/upload`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
    body,
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as JobInfo;
}

export async function readJob(token: string, jobId: string): Promise<JobInfo> {
  const response = await fetch(`${API}/jobs/${jobId}`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as JobInfo;
}

export async function readReport(token: string, jobId: string): Promise<JobReport> {
  const response = await fetch(`${API}/jobs/${jobId}/report`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  return (await response.json()) as JobReport;
}

export async function watchJob(
  token: string,
  jobId: string,
  onEvent: (job: JobInfo) => void,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API}/jobs/${jobId}/events`, {
    headers: { authorization: `Bearer ${token}` },
    signal,
  });
  if (!response.ok || response.body === null) {
    throw new Error(await readError(response));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const step = await reader.read();
    if (step.done) {
      break;
    }
    buffer += decoder.decode(step.value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      for (const line of part.split("\n")) {
        if (!line.startsWith("data: ")) {
          continue;
        }
        onEvent(JSON.parse(line.slice(6)) as JobInfo);
      }
    }
  }
}
