import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";
import {
  getProjectId,
  apiGet,
  apiDelete,
  apiPost,
} from "../helpers/common";

async function getScanDetails(
  page: any,
  projectId: number,
  runId: number
): Promise<{
  status: string;
  tool_ids: string[];
  tool_runs: Array<{
    tool: string | null;
    status: string | null;
    findings_count: number;
  }>;
}> {
  return apiGet(page, `/projects/${projectId}/scans/${runId}`);
}

async function getToolsWithFindings(
  page: any,
  projectId: number,
  runId: number
): Promise<Set<string>> {
  const details = await getScanDetails(page, projectId, runId);
  const toolsWithFindings = new Set<string>();
  for (const toolRun of details.tool_runs) {
    if (toolRun.tool && toolRun.findings_count > 0) {
      toolsWithFindings.add(toolRun.tool);
    }
  }
  return toolsWithFindings;
}

test.describe.serial("Journey 13: Scan Options and Saved Scans", () => {
  test("runs a single-tool scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    await scansPage.goto();
    await scansPage.openAdvancedOptions();
    await scansPage.selectSingleTool("semgrep");
    await scansPage.toggleSkipEnrichment();
    await scansPage.startScan();

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();

    const findings = await apiGet<{ items: any[]; total: number }>(
      page,
      `/projects/${projectId}/findings?limit=1000`
    );

    const toolsInFindings = new Set(findings.items.map((f: any) => f.tool));
    expect(toolsInFindings.has("semgrep")).toBe(true);
    expect(toolsInFindings.size).toBe(1);
  });

  test("runs a SAST segment scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);

    await scansPage.goto();
    await scansPage.openAdvancedOptions();
    await scansPage.selectDomainForScan("sast");
    await scansPage.toggleSkipEnrichment();
    await scansPage.startScan();

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();

    const projectId = await getProjectId(page);
    const findings = await apiGet<{ items: any[]; total: number }>(
      page,
      `/projects/${projectId}/findings?limit=1000`
    );

    const toolsInFindings = new Set(findings.items.map((f: any) => f.tool));
    const sastTools = ["semgrep", "noir"];
    const nonSastTools = ["gitleaks", "trufflehog", "katana", "nuclei"];
    for (const tool of sastTools) {
      expect(toolsInFindings.has(tool)).toBe(true);
    }
    for (const tool of nonSastTools) {
      expect(toolsInFindings.has(tool)).toBe(false);
    }
  });

  test("runs scan excluding specific tools", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    await scansPage.goto();
    await scansPage.openAdvancedOptions();
    await scansPage.excludeTool("gitleaks");
    await scansPage.excludeTool("trufflehog");
    await scansPage.toggleSkipEnrichment();
    await scansPage.startScan();

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();

    const findings = await apiGet<{ items: any[]; total: number }>(
      page,
      `/projects/${projectId}/findings?limit=1000`
    );

    const toolsInFindings = new Set(findings.items.map((f: any) => f.tool));
    expect(toolsInFindings.has("gitleaks")).toBe(false);
    expect(toolsInFindings.has("trufflehog")).toBe(false);
    expect(toolsInFindings.size).toBeGreaterThan(0);
  });

  test("creates saved scan from current options", async ({ scansPage, page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    await scansPage.goto();
    await scansPage.openAdvancedOptions();
    await scansPage.selectDomainForScan("sast");
    await scansPage.toggleSkipEnrichment();

    await scansPage.switchToSavedTab();
    const dialog = page.locator("[data-testid='save-scan-dialog']");
    try {
      const isVisible = await dialog.isVisible({ timeout: 1000 });
      if (!isVisible) {
        const newButton = page.getByRole("button", { name: /new/i });
        const newButtonVisible = await newButton
          .isVisible({ timeout: 1000 })
          .catch(() => false);
        if (newButtonVisible) {
          await newButton.click();
        }
      }
    } catch {
      const newButton = page.getByRole("button", { name: /new/i });
      const newButtonVisible = await newButton
        .isVisible({ timeout: 1000 })
        .catch(() => false);
      if (newButtonVisible) {
        await newButton.click();
      }
    }

    await scansPage.fillSavedScanName("SAST-Quick");
    await scansPage.saveScanConfig();
    await page.waitForTimeout(1000);

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );

    const foundScan = (savedScans.items ?? []).find(
      (s: any) => s.name === "SAST-Quick"
    );
    expect(foundScan).toBeDefined();
    expect(foundScan?.segments).toContain("sast");
    expect(foundScan?.skipEnrichment).toBe(true);
  });

  test("lists saved scans", async ({ scansPage, page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    await scansPage.goto();
    await scansPage.switchToSavedTab();

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );

    expect(savedScans.items.length).toBeGreaterThan(0);
    const foundName = savedScans.items[0]?.name;
    expect(foundName).toBeTruthy();
    await scansPage.expectSavedScanInList(foundName);
  });

  test("edits saved scan name", async ({ scansPage, page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const targetScan = savedScans.items.find((s: any) => s.name === "SAST-Quick");
    expect(targetScan).toBeDefined();

    await scansPage.goto();
    await scansPage.switchToSavedTab();
    await scansPage.selectSavedScan("SAST-Quick");

    await scansPage.fillSavedScanName("SAST-Quick-Renamed");
    await scansPage.saveScanConfig();
    await page.waitForTimeout(1000);

    const updated = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );

    const renamedScan = updated.items.find(
      (s: any) => s.name === "SAST-Quick-Renamed"
    );
    expect(renamedScan).toBeDefined();
  });

  test("executes saved scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    await scansPage.goto();
    await scansPage.switchToSavedTab();
    await scansPage.selectSavedScan("SAST-Quick-Renamed");
    await scansPage.runSavedScan();

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();

    await expect(page.locator("[data-testid='scan-status']")).toHaveText(
      /completed|done/i,
      { timeout: 30_000 }
    );

    const runs = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/scans?limit=1`
    );
    const runId = runs.items?.[0]?.id;
    expect(runId).toBeDefined();

    const toolsWithFindings = await getToolsWithFindings(
      page,
      projectId,
      runId
    );
    const sastTools = ["semgrep", "noir"];
    const nonSastTools = [
      "gitleaks", "trufflehog", "katana", "nuclei",
    ];
    for (const tool of sastTools) {
      expect(
        toolsWithFindings.has(tool),
        `Expected ${tool} to have findings in SAST scan`
      ).toBe(true);
    }
    for (const tool of nonSastTools) {
      expect(
        toolsWithFindings.has(tool),
        `${tool} should not have findings in SAST scan`
      ).toBe(false);
    }
  });

  test("loads saved scan into form", async ({ scansPage, page }) => {
    test.setTimeout(30_000);

    await scansPage.goto();
    await scansPage.switchToSavedTab();
    await scansPage.selectSavedScan("SAST-Quick-Renamed");

    const nameField = page.locator("#saved-scan-name");
    const value = await nameField.inputValue();
    expect(value).toBe("SAST-Quick-Renamed");
  });

  test("deletes saved scan", async ({ scansPage, page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    await scansPage.goto();
    await scansPage.switchToSavedTab();
    await scansPage.selectSavedScan("SAST-Quick-Renamed");
    await scansPage.deleteSavedScan();

    page.once("dialog", (dialog) => dialog.accept());

    await page.waitForTimeout(1000);

    const remaining = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );

    const stillExists = remaining.items.some(
      (s: any) => s.name === "SAST-Quick-Renamed"
    );
    expect(stillExists).toBe(false);
  });

  test("verifies scan appears in history", async ({ scansPage, page }) => {
    test.setTimeout(30_000);

    await scansPage.goto();
    await scansPage.switchToHistoryTab();

    const historyStatus = page.locator("[data-testid='scan-status']");
    await expect(historyStatus).toBeVisible({ timeout: 30_000 });
  });

  test("picks custom argument profile for scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    const profileName = "Gitleaks Test Profile";
    const profile = {
      toolName: "gitleaks",
      name: profileName,
      arguments: [{ flag: "-v", value: "" }],
    };

    const profileResult = await apiPost<{ id: number }>(
      page,
      `/projects/${projectId}/tools/arg-profiles`,
      {
        toolName: profile.toolName,
        name: profile.name,
        arguments: profile.arguments,
      }
    );

    expect(profileResult).toBeDefined();

    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/arg-profiles`
    );
    const createdProfile = profiles.items.find(
      (p: any) => p.name === profileName
    );
    expect(createdProfile).toBeDefined();

    await scansPage.goto();
    await scansPage.openAdvancedOptions();
    await scansPage.toggleSkipEnrichment();

    await scansPage.selectArgProfile(profileName);

    await scansPage.startScan();

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();

    await expect(page.locator("[data-testid='scan-status']")).toHaveText(
      /completed/i,
      { timeout: TIMEOUTS.scan }
    );

    await apiDelete(
      page,
      `/projects/${projectId}/tools/arg-profiles/${createdProfile.id}`
    );
  });
});
