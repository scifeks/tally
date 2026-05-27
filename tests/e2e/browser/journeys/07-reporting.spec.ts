import { test, expect } from "../fixtures/base";
import { Page } from "@playwright/test";
import {
  getProjectId,
  apiGet,
  apiPatch,
  apiDelete,
  apiPost,
} from "../helpers/common";
import { TIMEOUTS } from "../fixtures/constants";

interface Finding {
  id: number;
}

interface DraftResponse {
  drafts: Array<{
    section: string;
    status: "not_generated" | "generating" | "draft" | "reviewed" | "failed";
  }>;
}

interface ReportSummary {
  id: number;
  status: string;
  file_size_bytes?: number;
  display_name?: string;
  notes?: string;
  filename: string;
  format: string;
}

interface ReportsListResponse {
  items: ReportSummary[];
  total: number;
}

async function waitForDraftsIdle(page: Page, projectId: number): Promise<void> {
  await expect.poll(
    async () => {
      const response = await apiGet<DraftResponse>(
        page,
        `/projects/${projectId}/reports/drafts`
      );
      return response.drafts.every((d) => d.status !== "generating");
    },
    { timeout: TIMEOUTS.reportGeneration, intervals: [2000] }
  ).toBe(true);
}

test.describe.serial("Journey 7: Reporting", () => {
  let projectId: number;
  let findingIds: number[] = [];
  let generatedReportId: number | null = null;

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("marks findings for reporting via API", async ({ page }) => {
    projectId = await getProjectId(page);
    expect(projectId).toBeGreaterThan(0);

    const findingsResponse = await apiGet<{
      items: Finding[];
      total: number;
    }>(page, `/projects/${projectId}/findings?limit=20`);

    expect(findingsResponse.total).toBeGreaterThan(0);

    findingIds = findingsResponse.items.slice(0, 15).map(f => f.id);
    expect(findingIds.length).toBeGreaterThan(0);

    const patchResponse = await apiPatch<{
      updated: number[];
      skipped_locked: number[];
      not_found: number[];
    }>(page, `/projects/${projectId}/findings/batch`, {
      ids: findingIds,
      should_report: true,
    });

    expect(patchResponse.updated.length).toBeGreaterThan(0);
  });

  test("navigates to reports page and fills metadata", async ({
    reportsPage,
    page,
  }) => {
    await reportsPage.goto();
    await expect(page).toHaveURL(/\/reports/);

    await reportsPage.selectFormat("pdf");
    await reportsPage.fillCompanyName("E2E Test Corp");

    const today = new Date().toISOString().split("T")[0];
    await reportsPage.fillEngagementDate(today);

    await expect(
      page.getByText("Draft Sections", { exact: true })
    ).toBeVisible();
  });

  test("generates executive-summary draft", async ({ reportsPage, page }) => {
    test.setTimeout(TIMEOUTS.reportGeneration);
    await waitForDraftsIdle(page, projectId);

    const sections = [
      "executive-summary", "risk-level", "critical-issues",
      "improvement-points", "scope-and-methodology",
      "general-recommendations",
    ];
    for (const s of sections) {
      await apiDelete(page, `/projects/${projectId}/reports/drafts/${s}`)
        .catch(() => {});
    }

    await reportsPage.goto();
    await reportsPage.generateDraftSection("executive-summary");

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        return response.drafts.find(
          (d) => d.section === "executive-summary"
        )?.status;
      },
      { timeout: TIMEOUTS.reportGeneration, intervals: [2000] }
    ).toBe("draft");
  });

  test("generates all missing drafts", async ({ reportsPage, page }) => {
    test.setTimeout(300_000);
    await reportsPage.goto();
    await waitForDraftsIdle(page, projectId);
    await reportsPage.clickGenerateMissing();

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        return response.drafts.every(
          (d) => d.status === "draft" || d.status === "reviewed"
        );
      },
      { timeout: 300_000, intervals: [3000] }
    ).toBe(true);
  });

  test("regenerates an existing draft", async ({ reportsPage, page }) => {
    test.setTimeout(TIMEOUTS.reportGeneration);
    await reportsPage.goto();
    await waitForDraftsIdle(page, projectId);
    await reportsPage.clickRegenerate("executive-summary");

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        return response.drafts.find(
          (d) => d.section === "executive-summary"
        )?.status;
      },
      { timeout: TIMEOUTS.reportGeneration, intervals: [2000] }
    ).toBe("draft");
  });

  test("deletes a draft and regenerates", async ({ reportsPage, page }) => {
    test.setTimeout(TIMEOUTS.reportGeneration);
    await reportsPage.goto();
    await waitForDraftsIdle(page, projectId);

    const drafts = await apiGet<DraftResponse>(
      page,
      `/projects/${projectId}/reports/drafts`
    );
    const initialStatus = drafts.drafts.find(
      d => d.section === "scope-and-methodology"
    )?.status;
    expect(initialStatus).toBeTruthy();

    page.once("dialog", (dialog) => dialog.accept());
    await reportsPage.deleteDraft("scope-and-methodology");

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        return response.drafts.find(
          d => d.section === "scope-and-methodology"
        )?.status;
      },
      { timeout: 10_000, intervals: [500] }
    ).toBe("not_generated");

    await reportsPage.goto();
    await reportsPage.generateDraftSection("scope-and-methodology");

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        return response.drafts.find(
          d => d.section === "scope-and-methodology"
        )?.status;
      },
      { timeout: TIMEOUTS.reportGeneration, intervals: [2000] }
    ).toBe("draft");
  });

  test("generates full report", async ({ reportsPage, page }) => {
    test.setTimeout(TIMEOUTS.reportGeneration);
    await reportsPage.goto();
    await waitForDraftsIdle(page, projectId);
    await reportsPage.clickGenerateReport();

    await expect.poll(
      async () => {
        const response = await apiGet<ReportsListResponse>(
          page,
          `/projects/${projectId}/reports?limit=1`
        );
        if (response.items?.length > 0) {
          const report = response.items[0];
          if (report.status === "done") {
            generatedReportId = report.id;
            return "done";
          }
          return report.status;
        }
        return "not_found";
      },
      { timeout: TIMEOUTS.reportGeneration, intervals: [3000] }
    ).toBe("done");

    expect(generatedReportId).toBeGreaterThan(0);
  });

  test("verifies report in history", async ({ reportsPage, page }) => {
    await reportsPage.goto();

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=5`
    );

    expect(reports.items.length).toBeGreaterThan(0);
    expect(reports.items[0].status).toBe("done");

    const historyRows = page.locator(
      "[data-testid^='report-history-row-']"
    );
    const count = await historyRows.count();
    expect(count).toBeGreaterThan(0);
  });

  test("edits report display name", async ({ page }) => {
    expect(generatedReportId).toBeTruthy();

    const newName = "E2E Test Report - Updated";
    await apiPatch(
      page,
      `/projects/${projectId}/reports/${generatedReportId}`,
      { display_name: newName }
    );

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=1`
    );
    expect(reports.items[0].display_name).toBe(newName);
  });

  test("edits report notes", async ({ page }) => {
    expect(generatedReportId).toBeTruthy();

    const newNotes = "Test notes for E2E reporting";
    await apiPatch(
      page,
      `/projects/${projectId}/reports/${generatedReportId}`,
      { notes: newNotes }
    );

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=1`
    );
    expect(reports.items[0].notes).toBe(newNotes);
  });

  test("downloads report", async ({ page }) => {
    expect(generatedReportId).toBeTruthy();

    const reportId = generatedReportId!;

    const downloadResponse = await page.evaluate(
      async (params: { base: string; pid: number; rid: number }) => {
        const res = await fetch(
          `${params.base}/projects/${params.pid}/reports/${params.rid}/download`
        );
        const body = await res.arrayBuffer();
        return {
          status: res.status,
          contentType: res.headers.get("content-type"),
          contentLength:
            res.headers.get("content-length") || body.byteLength,
        };
      },
      {
        base: "http://127.0.0.1:3100/api/v1",
        pid: projectId,
        rid: reportId,
      }
    );

    expect(downloadResponse.status).toBe(200);
    expect(downloadResponse.contentType).toBeTruthy();
    expect(Number(downloadResponse.contentLength)).toBeGreaterThan(0);
  });

  test("verifies report metadata survives reload", async ({ page }) => {
    expect(generatedReportId).toBeTruthy();

    const testName = "Reload Test Report";
    const testNotes = "Reload test notes";
    await apiPatch(
      page,
      `/projects/${projectId}/reports/${generatedReportId}`,
      { display_name: testName, notes: testNotes }
    );

    await page.reload();

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=10`
    );
    const reloadedReport = reports.items.find(
      (r) => r.id === generatedReportId
    );
    expect(reloadedReport).toBeDefined();
    expect(reloadedReport!.display_name).toBe(testName);
    expect(reloadedReport!.notes).toBe(testNotes);
  });

  test("deletes report", async ({ page }) => {
    expect(generatedReportId).toBeTruthy();

    await apiDelete(
      page,
      `/projects/${projectId}/reports/${generatedReportId}`
    );

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=10`
    );
    const deleted = reports.items.find(r => r.id === generatedReportId);
    expect(deleted).toBeUndefined();
  });
});
