import { test, expect } from "../fixtures/base";
import { API_DIRECT, TIMEOUTS } from "../fixtures/constants";

test.describe.serial("Journey 3: Scan Execution", () => {
  test("starts scan and waits for completion", async ({
    scansPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.scan);
    await scansPage.goto();

    const projectId = await page.evaluate(async () => {
      const res = await fetch("/api/v1/projects");
      const body = await res.json();
      return body.items ? body.items[0].id : body[0].id;
    });

    await page.evaluate(async (pid: number) => {
      await fetch(`/api/v1/projects/${pid}/scans`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          skipEnrichment: true,
          domains: ["sast", "sca", "secrets"],
        }),
      });
    }, projectId);

    await scansPage.waitForScanComplete();
  });

  test("verifies scan in history tab", async ({ scansPage }) => {
    await scansPage.goto();
    await scansPage.switchToHistoryTab();
    await scansPage.expectScanStatus("done");
  });

  test("verifies findings produced via API", async ({ page }) => {
    const projectsRes = await page.request.get(
      `${API_DIRECT}/projects`
    );
    const projectsBody = await projectsRes.json();
    const projectId = projectsBody.items
      ? projectsBody.items[0].id
      : projectsBody[0].id;

    const findingsRes = await page.request.get(
      `${API_DIRECT}/projects/${projectId}/findings?limit=1`
    );
    const findingsBody = await findingsRes.json();
    expect(findingsBody.total).toBeGreaterThan(0);
  });
});

test.describe.serial("Journey 3b: Scan UI Interactions", () => {
  test("verifies scan page loads with controls", async ({
    scansPage,
    page,
  }) => {
    await scansPage.goto();
    await expect(page).toHaveURL(/\/scans/);
    await expect(
      page.getByRole("button", { name: /Start Scan/i })
    ).toBeVisible();
  });

  test("verifies tabs are present", async ({ scansPage, page }) => {
    await scansPage.goto();
    await expect(
      page.getByText("Live Log", { exact: true })
    ).toBeVisible();
    await expect(
      page.getByText("History", { exact: true })
    ).toBeVisible();
    await expect(
      page.getByText("Saved Scans", { exact: true })
    ).toBeVisible();
  });

  test("switches to History tab", async ({ scansPage, page }) => {
    await scansPage.goto();
    await scansPage.switchToHistoryTab();
    await page.waitForTimeout(500);
  });

  test("switches to Saved Scans tab", async ({
    scansPage,
    page,
  }) => {
    await scansPage.goto();
    await scansPage.switchToSavedTab();
    await page.waitForTimeout(500);
  });

  test("cancels a running scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    await scansPage.goto();
    await scansPage.startScan();
    await page.waitForTimeout(3000);
    await scansPage.cancelScan();
    await expect(
      page.getByText(/cancel|stopped/i).first()
    ).toBeVisible({ timeout: 30_000 });
  });
});
