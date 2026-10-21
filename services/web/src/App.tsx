import { useEffect, useState } from "react";

export function App() {
  const [health, setHealth] = useState("checking");

  useEffect(() => {
    void fetch("/health")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`health ${response.status}`);
        }
        const body = (await response.json()) as { status: string };
        setHealth(body.status);
      })
      .catch((err: unknown) => {
        setHealth(err instanceof Error ? err.message : "health request failed");
      });
  }, []);

  return (
    <main>
      <h1>LegacyLift</h1>
      <p>
        Upload a legacy Python 2.7 project, pin its behaviour with tests, and migrate it
        to Python 3.12 after those tests pass in a sandbox.
      </p>
      <p>UI health: {health}</p>
      <p>Job upload and live progress land in M5. This page is the M0 shell.</p>
    </main>
  );
}
