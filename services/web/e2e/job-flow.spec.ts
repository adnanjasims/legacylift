import { expect, test, type Page } from "@playwright/test";

const report = {
  job_id: "job1",
  source: "https://example.com/repo.git",
  mode: "deterministic",
  provider: null,
  model_id: null,
  files: [
    {
      path: "pricing.py",
      status: "verified",
      tests_before_passed: 21,
      tests_before_failed: 0,
      tests_after_passed: 21,
      tests_after_failed: 0,
      compile_ok: true,
      diff: "--- a/pricing.py\n+++ b/pricing.py\n@@ -1 +1 @@\n-print 1\n+print(1)\n",
      after_failures: [],
      attempts: 1,
      llm_used: false,
    },
  ],
  notes: [],
  wall_clock_sec: 4.2,
  usage: [],
};

async function mockApi(page: Page): Promise<void> {
  await page.route("**/api/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        token: "test-token",
        username: "alice",
        role: "user",
      }),
    });
  });
  await page.route("**/api/jobs/job1/report", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(report),
    });
  });
  await page.route("**/api/jobs/job1/events", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: 'data: {"id":"job1","source":"https://example.com/repo.git","status":"completed","attempt":1,"error":null,"report_dir":"/tmp/x"}\n\n',
    });
  });
  await page.route("**/api/jobs/job1", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "job1",
        source: "https://example.com/repo.git",
        status: "completed",
        attempt: 1,
        error: null,
        report_dir: "/tmp/x",
      }),
    });
  });
  await page.route("**/api/jobs", async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "job1",
        source: "https://example.com/repo.git",
        status: "queued",
        attempt: 0,
        error: null,
        report_dir: null,
      }),
    });
  });
}

test("login, start a job, and show the diff", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByLabel("Password").fill("dev-alice");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Signed in as alice")).toBeVisible();
  await page.getByLabel("Git URL").fill("https://example.com/repo.git");
  await page.getByRole("button", { name: "Run migration" }).click();
  await expect(page.getByRole("heading", { name: "Report" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "pricing.py" })).toBeVisible();
  await expect(page.getByText("+print(1)")).toBeVisible();
});
