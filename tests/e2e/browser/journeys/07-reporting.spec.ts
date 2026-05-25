import { test, expect } from "../fixtures/base";
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

test.describe.serial("Journey 7: Reporting", () => {
  let projectId: number;
  let findingIds: number[] = [];
  let generatedReportId: number | null = null;
  let draftGeneratedReportId: number | null = null;

  test("marks findings for reporting via API", async ({ page }) => {
    await page.goto("/");

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
      updated: number;
      skipped_locked: number;
      not_found: number;
    }>(page, `/projects/${projectId}/findings/batch`, {
      ids: findingIds,
      should_report: true,
    });

    expect(patchResponse.updated).toBeGreaterThan(0);
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

  test("generates executive_summary draft", async ({ reportsPage, page }) => {
    await reportsPage.generateDraftSection("executive_summary");

    await expect.poll(
      async () => {
        const response = await page.evaluate(
          async (base: string) => {
            const res = await fetch(
              `${base}/projects/${projectId}/reports/drafts`
            );
            return res.json();
          },
          "http://127.0.0.1:3100/api/v1"
        );
        const summary = response.drafts.find(
          (d: { section: string }) => d.section === "executive_summary"
        );
        return summary?.status;
      },
      {
        timeout: TIMEOUTS.reportGeneration,
        intervals: [2000],
      }
    ).toBe("draft");

    const drafts = await apiGet<DraftResponse>(
      page,
      `/projects/${projectId}/reports/drafts`
    );
    const execSummary = drafts.drafts.find(d => d.section === "executive_summary");
    expect(execSummary?.status).toBe("draft");
  });

  test("generates all missing drafts", async ({ reportsPage, page }) => {
    await reportsPage.clickGenerateMissing();

    await expect.poll(
      async () => {
        const response = await page.evaluate(
          async (base: string) => {
            const res = await fetch(
              `${base}/projects/${projectId}/reports/drafts`
            );
            return res.json();
          },
          "http://127.0.0.1:3100/api/v1"
        );
        const allDone = response.drafts.every(
          (d: { status: string }) =>
            d.status === "draft" || d.status === "reviewed"
        );
        return allDone;
      },
      {
        timeout: 300_000,
        intervals: [3000],
      }
    ).toBe(true);

    const drafts = await apiGet<DraftResponse>(
      page,
      `/projects/${projectId}/reports/drafts`
    );
    const allReady = drafts.drafts.every(
      d => d.status === "draft" || d.status === "reviewed"
    );
    expect(allReady).toBe(true);
  });

  test("regenerates an existing draft", async ({ reportsPage, page }) => {
    await reportsPage.clickGenerateMissing();

    await expect.poll(
      async () => {
        const response = await page.evaluate(
          async (base: string) => {
            const res = await fetch(
              `${base}/projects/${projectId}/reports/drafts`
            );
            return res.json();
          },
          "http://127.0.0.1:3100/api/v1"
        );
        const summary = response.drafts.find(
          (d: { section: string }) => d.section === "executive_summary"
        );
        return summary?.status;
      },
      {
        timeout: TIMEOUTS.reportGeneration,
        intervals: [2000],
      }
    ).toBe("draft");
  });

  test("deletes a draft and regenerates", async ({ reportsPage, page }) => {
    let drafts = await apiGet<DraftResponse>(
      page,
      `/projects/${projectId}/reports/drafts`
    );
    const initialMethodologyStatus = drafts.drafts.find(
      d => d.section === "methodology"
    )?.status;
    expect(initialMethodologyStatus).toBeTruthy();

    await reportsPage.deleteDraft("methodology");

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        const methodology = response.drafts.find(
          d => d.section === "methodology"
        );
        return methodology?.status;
      },
      {
        timeout: 10_000,
        intervals: [500],
      }
    ).toBe("not_generated");

    await reportsPage.generateDraftSection("methodology");

    await expect.poll(
      async () => {
        const response = await apiGet<DraftResponse>(
          page,
          `/projects/${projectId}/reports/drafts`
        );
        const methodology = response.drafts.find(
          d => d.section === "methodology"
        );
        return methodology?.status;
      },
      {
        timeout: TIMEOUTS.reportGeneration,
        intervals: [2000],
      }
    ).toBe("draft");
  });

  test("generates full report", async ({ reportsPage, page }) => {
    await reportsPage.clickGenerateReport();

    await expect.poll(
      async () => {
        const response = await page.evaluate(
          async (base: string) => {
            const res = await fetch(
              `${base}/projects/${projectId}/reports?limit=1`
            );
            return res.json();
          },
          "http://127.0.0.1:3100/api/v1"
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
      {
        timeout: TIMEOUTS.reportGeneration,
        intervals: [3000],
      }
    ).toBe("done");

    expect(generatedReportId).toBeGreaterThan(0);

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=1`
    );
    expect(reports.items[0].status).toBe("done");
    expect(reports.items[0].file_size_bytes).toBeGreaterThan(0);
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

  test("edits report display name", async ({ reportsPage, page }) => {
    expect(generatedReportId).toBeTruthy();

    await reportsPage.goto();

    await reportsPage.selectReportFromHistory(generatedReportId!);

    await expect(
      page.locator("[data-testid='report-detail-name']")
    ).toBeVisible();

    const newName = "E2E Test Report - Updated";
    await apiPatch(
      page,
      `/projects/${projectId}/reports/${generatedReportId}`,
      {
        display_name: newName,
      }
    );

    const reports = await apiGet<ReportsListResponse>(
      page,
      `/projects/${projectId}/reports?limit=1`
    );
    expect(reports.items[0].display_name).toBe(newName);
  });

  test("edits report notes", async ({ reportsPage, page }) => {
    expect(generatedReportId).toBeTruthy();

    await reportsPage.goto();

    await reportsPage.selectReportFromHistory(generatedReportId!);

    const newNotes = "Test notes for E2E reporting";
    await apiPatch(
      page,
      `/projects/${projectId}/reports/${generatedReportId}`,
      {
        notes: newNotes,
      }
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
      async (params: {
        base: string;
        pid: number;
        rid: number;
      }) => {
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

  test("verifies report metadata survives reload", async ({ page }) => {
    expect(generatedReportId).toBeTruthy();

    const testName = "Reload Test Report";
    const testNotes = "Reload test notes";
    await apiPatch(page, `/projects/${projectId}/reports/${generatedReportId}`, {
      display_name: testName,
      notes: testNotes,
    });

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
});
