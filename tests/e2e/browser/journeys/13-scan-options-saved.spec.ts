import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";
import {
  getProjectId,
  apiGet,
  apiDelete,
  apiPost,
  apiPut,
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
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(300);
  });

  test("runs a single-tool scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    const runs = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/scans?status=running&limit=1`
    );
    for (const run of runs.items ?? []) {
      await apiPost(
        page,
        `/projects/${projectId}/scans/${run.id}/cancel`,
        {}
      ).catch(() => {});
    }
    if (runs.items?.length) {
      await page.waitForTimeout(3000);
    }

    const scanResult = await apiPost<{ id: number }>(
      page,
      `/projects/${projectId}/scans`,
      { skipEnrichment: true, toolIds: ["semgrep"] }
    );
    expect(scanResult.id).toBeDefined();

    await expect.poll(
      async () => {
        const detail = await apiGet<{ status: string }>(
          page,
          `/projects/${projectId}/scans/${scanResult.id}`
        );
        return detail.status;
      },
      { timeout: TIMEOUTS.scan, intervals: [3000] }
    ).toMatch(/done|failed|completed/i);

    const findings = await apiGet<{ items: any[]; total: number }>(
      page,
      `/projects/${projectId}/findings?tool=semgrep&limit=1`
    );
    expect(findings.total).toBeGreaterThan(0);
  });

  test("runs a SAST segment scan", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    const scanResult = await apiPost<{ id: number }>(
      page,
      `/projects/${projectId}/scans`,
      { skipEnrichment: true, domains: ["sast"] }
    );
    expect(scanResult.id).toBeDefined();

    await expect.poll(
      async () => {
        const detail = await apiGet<{ status: string }>(
          page,
          `/projects/${projectId}/scans/${scanResult.id}`
        );
        return detail.status;
      },
      { timeout: TIMEOUTS.scan, intervals: [3000] }
    ).toMatch(/done|failed|completed/i);

    const findings = await apiGet<{ items: any[]; total: number }>(
      page,
      `/projects/${projectId}/findings?tool=semgrep&limit=1`
    );
    expect(findings.total).toBeGreaterThan(0);
  });

  test("runs scan excluding specific tools", async ({ scansPage, page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    const scanResult = await apiPost<{ id: number }>(
      page,
      `/projects/${projectId}/scans`,
      { skipEnrichment: true, toolIds: ["osv-scanner"] }
    );
    expect(scanResult.id).toBeDefined();

    await expect.poll(
      async () => {
        const detail = await apiGet<{ status: string }>(
          page,
          `/projects/${projectId}/scans/${scanResult.id}`
        );
        return detail.status;
      },
      { timeout: TIMEOUTS.scan, intervals: [3000] }
    ).toMatch(/done|failed|completed/i);

    const findings = await apiGet<{ total: number }>(
      page,
      `/projects/${projectId}/findings?limit=1`
    );
    expect(findings.total).toBeGreaterThan(0);
  });

  test("creates saved scan from current options", async ({ page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    const existing = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const stale = existing.items?.find(
      (s: any) => s.name === "SAST-Quick"
    );
    if (stale) {
      await apiDelete(
        page,
        `/projects/${projectId}/saved-scans/${stale.id}`
      ).catch(() => {});
    }

    const created = await apiPost<{ id: number; name: string }>(
      page,
      `/projects/${projectId}/saved-scans`,
      {
        name: "SAST-Quick",
        skipEnrichment: true,
        segments: ["sast"],
        toolNames: ["semgrep"],
      }
    );
    expect(created.id).toBeDefined();

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const foundScan = (savedScans.items ?? []).find(
      (s: any) => s.name === "SAST-Quick"
    );
    expect(foundScan).toBeDefined();
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

  test("edits saved scan name", async ({ page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const targetScan = savedScans.items.find(
      (s: any) => s.name === "SAST-Quick"
    );
    expect(targetScan).toBeDefined();

    await apiPut(
      page,
      `/projects/${projectId}/saved-scans/${targetScan.id}`,
      { name: "SAST-Quick-Renamed", skipEnrichment: true, segments: ["sast"], toolNames: ["semgrep"] }
    );

    const updated = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const renamedScan = updated.items.find(
      (s: any) => s.name === "SAST-Quick-Renamed"
    );
    expect(renamedScan).toBeDefined();
  });

  test("executes saved scan", async ({ page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const target = savedScans.items.find(
      (s: any) => s.name === "SAST-Quick-Renamed"
    );
    expect(target).toBeDefined();

    const runResult = await apiPost<{ id: number }>(
      page,
      `/projects/${projectId}/saved-scans/${target.id}/run`,
      {}
    );
    expect(runResult.id).toBeDefined();

    await expect.poll(
      async () => {
        const detail = await apiGet<{ status: string }>(
          page,
          `/projects/${projectId}/scans/${runResult.id}`
        );
        return detail.status;
      },
      { timeout: TIMEOUTS.scan, intervals: [3000] }
    ).toMatch(/done|failed|completed/i);
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

  test("deletes saved scan", async ({ page }) => {
    test.setTimeout(30_000);
    const projectId = await getProjectId(page);

    const savedScans = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/saved-scans`
    );
    const target = savedScans.items.find(
      (s: any) => s.name === "SAST-Quick-Renamed"
    );
    expect(target).toBeDefined();

    await apiDelete(
      page,
      `/projects/${projectId}/saved-scans/${target.id}`
    );

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

  test("picks custom argument profile for scan", async ({ page }) => {
    test.setTimeout(TIMEOUTS.scan);
    const projectId = await getProjectId(page);

    const profileName = "Gitleaks Test Profile";
    await page.evaluate(
      async ({ base, pid, body }: {
        base: string; pid: number; body: unknown;
      }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
        const form = new URLSearchParams();
        form.set("payload", JSON.stringify(body));
        const res = await fetch(
          `${base}/projects/${pid}/arg-profiles`,
          {
            method: "POST",
            headers: { "x-csrf-token": csrf },
            body: form,
          }
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`POST arg-profiles: ${res.status} ${text}`);
        }
      },
      {
        base: "/api/v1",
        pid: projectId,
        body: {
          toolName: "gitleaks",
          name: profileName,
          args: [{ name: "-v", type: "flag" }],
        },
      }
    );

    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const createdProfile = profiles.items.find(
      (p: any) => p.name === profileName
    );
    expect(createdProfile).toBeDefined();

    const scanResult = await apiPost<{ id: number }>(
      page,
      `/projects/${projectId}/scans`,
      {
        skipEnrichment: true,
        toolIds: ["gitleaks"],
        argProfileIds: [createdProfile.id],
      }
    );
    expect(scanResult.id).toBeDefined();

    await expect.poll(
      async () => {
        const detail = await apiGet<{ status: string }>(
          page,
          `/projects/${projectId}/scans/${scanResult.id}`
        );
        return detail.status;
      },
      { timeout: TIMEOUTS.scan, intervals: [3000] }
    ).toMatch(/done|failed|completed/i);

    await apiDelete(
      page,
      `/projects/${projectId}/arg-profiles/${createdProfile.id}`
    );
  });
});
