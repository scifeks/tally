import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";
import { getProjectId, apiGet } from "../helpers/common";

test.describe.serial("Journey 3: Scan Execution", () => {
  test("cleans stale global tool overrides", async ({ page }) => {
    await page.goto("/");
    await page.evaluate(async () => {
      const projRes = await fetch("/api/v1/projects");
      const projBody = await projRes.json();
      const pid = projBody.items
        ? projBody.items[0].id
        : projBody[0].id;

      const csrf =
        document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";

      const ovRes = await fetch(
        `/api/v1/projects/${pid}/tools/overrides`
      );
      const ovBody = await ovRes.json();
      const globals = (ovBody.items ?? ovBody).filter(
        (o: { scope: string }) => o.scope === "global"
      );
      const toolNames = [
        ...new Set(
          globals.map((o: { toolName: string }) => o.toolName)
        ),
      ];
      for (const name of toolNames) {
        await fetch(
          `/api/v1/projects/${pid}/tools/overrides/${name}`,
          {
            method: "DELETE",
            headers: { "x-csrf-token": csrf },
          }
        );
      }
    });
  });

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
      const csrf =
        document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
      const catalogRes = await fetch(
        `/api/v1/projects/${pid}/scans/config`
      );
      const catalog = await catalogRes.json();
      const allTools = catalog.tools.map(
        (t: { id: string }) => t.id
      );
      const res = await fetch(`/api/v1/projects/${pid}/scans`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-csrf-token": csrf,
        },
        body: JSON.stringify({
          skipEnrichment: true,
          toolIds: allTools,
        }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`Scan start failed (${res.status}): ${body}`);
      }
    }, projectId);

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();
  });

  test("verifies scan in history tab", async ({ scansPage }) => {
    await scansPage.goto();
    await scansPage.switchToHistoryTab();
    await scansPage.expectScanStatus("done");
  });

  test("verifies findings produced via API", async ({ page }) => {
    await page.goto("/");
    const total = await page.evaluate(async () => {
      const projRes = await fetch("/api/v1/projects");
      const projBody = await projRes.json();
      const pid = projBody.items
        ? projBody.items[0].id
        : projBody[0].id;
      const findRes = await fetch(
        `/api/v1/projects/${pid}/findings?limit=1`
      );
      const findBody = await findRes.json();
      return findBody.total;
    });
    expect(total).toBeGreaterThan(0);
  });

  test("verifies every configured tool produced findings", async ({
    page,
  }) => {
    const pid = await getProjectId(page);
    const findings = await apiGet<{ items: any[]; total: number }>(
      page,
      `/projects/${pid}/findings?limit=1000`
    );

    const toolsWithFindings = new Set(findings.items.map((f: any) => f.tool));

    const expectedTools = [
      "semgrep",
      "gitleaks",
      "npm-audit",
      "pip-audit",
      "composer-audit",
      "noir",
    ];
    for (const tool of expectedTools) {
      expect(
        toolsWithFindings.has(tool),
        `Expected ${tool} to produce findings against DVECA`
      ).toBe(true);
    }
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
    await expect(page.locator('[role="tabpanel"]').first()).toBeVisible();
  });

  test("switches to Saved Scans tab", async ({
    scansPage,
    page,
  }) => {
    await scansPage.goto();
    await scansPage.switchToSavedTab();
    await expect(page.locator('[role="tabpanel"]').first()).toBeVisible();
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
