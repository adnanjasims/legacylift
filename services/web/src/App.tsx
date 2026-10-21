import { useEffect, useState, type FormEvent } from "react";

import {
  createJob,
  login,
  readJob,
  readReport,
  uploadJob,
  watchJob,
  type LoginResult,
} from "./api.ts";
import { costLabel, tokenLabel } from "./format.ts";
import type { FileReport, JobInfo, JobReport } from "./types.ts";

export function App() {
  const [session, setSession] = useState<LoginResult | null>(null);
  const [username, setUsername] = useState("alice");
  const [password, setPassword] = useState("");
  const [source, setSource] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [job, setJob] = useState<JobInfo | null>(null);
  const [report, setReport] = useState<JobReport | null>(null);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    if (session === null || job === null) {
      return;
    }
    const token = session.token;
    const jobId = job.id;
    const abort = new AbortController();
    void watchJob(token, jobId, setJob, abort.signal).catch(() => {
      /* Poll below covers a dropped SSE stream. */
    });
    const timer = window.setInterval(() => {
      void readJob(token, jobId)
        .then(setJob)
        .catch((err: unknown) => {
          setError(err instanceof Error ? err.message : "job status failed");
        });
    }, 2000);
    return () => {
      abort.abort();
      window.clearInterval(timer);
    };
  }, [session, job?.id]);

  useEffect(() => {
    if (session === null || job === null || job.status !== "completed") {
      return;
    }
    void readReport(session.token, job.id)
      .then((body) => {
        setReport(body);
        setSelected(body.files[0]?.path ?? "");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "report failed");
      });
  }, [session, job]);

  async function onLogin(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSession(await login(username, password));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (session === null) {
      return;
    }
    setBusy(true);
    setError("");
    setReport(null);
    try {
      const created =
        zipFile !== null
          ? await uploadJob(session.token, zipFile)
          : await createJob(session.token, source.trim());
      setJob(created);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "job create failed");
    } finally {
      setBusy(false);
    }
  }

  const current: FileReport | undefined = report?.files.find(
    (item) => item.path === selected,
  );

  return (
    <main>
      <h1>LegacyLift</h1>
      <p>
        Upload a Python 2.7 zip or point at an https git URL. Characterization tests run
        on the original code in Docker, then 2to3 runs, then the same tests run on
        Python 3.12. A file is verified only when those tests still pass.
      </p>

      {session === null ? (
        <form onSubmit={(event) => void onLogin(event)}>
          <h2>Sign in</h2>
          <label>
            Username
            <input
              name="username"
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>
          <button type="submit" disabled={busy}>
            Sign in
          </button>
        </form>
      ) : (
        <p>
          Signed in as {session.username} ({session.role}).
        </p>
      )}

      {session !== null ? (
        <form onSubmit={(event) => void onSubmit(event)}>
          <h2>Start a job</h2>
          <label>
            Git URL
            <input
              name="source"
              type="text"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="https://github.com/example/repo.git"
            />
          </label>
          <label>
            Zip upload
            <input
              name="zip"
              type="file"
              accept=".zip"
              onChange={(event) => setZipFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <button
            type="submit"
            disabled={busy || (zipFile === null && source.trim() === "")}
          >
            Run migration
          </button>
        </form>
      ) : null}

      {error ? <p role="alert">{error}</p> : null}

      {job ? (
        <section>
          <h2>Job {job.id}</h2>
          <p>Status: {job.status}</p>
          {job.error ? <p>Error: {job.error}</p> : null}
          {job.status === "queued" || job.status === "running" ? (
            <p>Waiting for the worker. This page polls and listens for events.</p>
          ) : null}
        </section>
      ) : null}

      {report ? (
        <section>
          <h2>Report</h2>
          <p>
            Mode {report.mode}. Tokens {tokenLabel(report)}. Cost USD{" "}
            {costLabel(report)}. Wall clock {report.wall_clock_sec.toFixed(1)}s.
          </p>
          {report.notes.length === 0 ? null : (
            <ul>
              {report.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
          {report.files.length === 0 ? (
            <p>No files in this report.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Before</th>
                  <th>After</th>
                  <th>Attempts</th>
                </tr>
              </thead>
              <tbody>
                {report.files.map((item) => (
                  <tr key={item.path}>
                    <td>
                      <button type="button" onClick={() => setSelected(item.path)}>
                        {item.path}
                      </button>
                    </td>
                    <td>{item.status}</td>
                    <td>
                      {item.tests_before_passed}/{item.tests_before_failed}
                    </td>
                    <td>
                      {item.tests_after_passed}/{item.tests_after_failed}
                    </td>
                    <td>{item.attempts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {current ? (
            <div>
              <h3>{current.path}</h3>
              {current.after_failures.length === 0 ? (
                <p>No after-migration failures recorded for this file.</p>
              ) : (
                <pre>{current.after_failures.join("\n")}</pre>
              )}
              {current.diff ? (
                <pre>{current.diff}</pre>
              ) : (
                <p>No diff. The file matched after 2to3.</p>
              )}
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
