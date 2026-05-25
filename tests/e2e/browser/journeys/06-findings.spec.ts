import { test, expect } from "../fixtures/base";
import { getProjectId, apiGet, apiPost, apiPatch } from "../helpers/common";

test.describe.serial("Journey 6: Findings Review", () => {
  const severities = ["critical", "high", "medium", "low"];
  const testFindingTitles: Record<string, string> = {};
  test("navigates to findings page", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await expect(page).toHaveURL(/\/findings/);
    await findingsPage.expectFindingsVisible();
  });

  test("verifies finding count matches API", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { id: number }[];
      total: number;
    }>(page, `/projects/${pid}/findings?limit=1`);

    expect(response.total).toBeGreaterThan(0);
  });
  test("filters by critical severity", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.toggleSeverityFilter("critical");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { severity: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?severity=critical&limit=50`);

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      expect(f.severity).toBe("critical");
    }
  });

  test("filters by high severity", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.toggleSeverityFilter("high");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { severity: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?severity=high&limit=50`);

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      expect(f.severity).toBe("high");
    }
  });

  test("filters by medium severity", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.toggleSeverityFilter("medium");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { severity: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?severity=medium&limit=50`);

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      expect(f.severity).toBe("medium");
    }
  });

  test("filters by low severity", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.toggleSeverityFilter("low");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { severity: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?severity=low&limit=50`);

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      expect(f.severity).toBe("low");
    }
  });

  test("clears severity filters", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.toggleSeverityFilter("critical");
    await page.waitForTimeout(300);
    await findingsPage.clearFilters();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );

    expect(response.total).toBeGreaterThan(0);
  });
  test("filters by semgrep tool", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { tool: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?tool=semgrep&limit=50`);

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      expect(f.tool).toBe("semgrep");
    }
  });

  test("filters by gitleaks tool", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { tool: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?tool=gitleaks&limit=50`);

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      expect(f.tool).toBe("gitleaks");
    }
  });
  test("sorts by severity descending", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { severity: string }[];
    }>(
      page,
      `/projects/${pid}/findings?sort=severity&order=desc&limit=10`
    );

    expect(response.items.length).toBeGreaterThan(1);
    const rank: Record<string, number> = {
      critical: 4, high: 3, medium: 2, low: 1, informational: 0,
    };
    for (let i = 1; i < response.items.length; i++) {
      const prev = rank[response.items[i - 1].severity] ?? 0;
      const curr = rank[response.items[i].severity] ?? 0;
      expect(prev).toBeGreaterThanOrEqual(curr);
    }
  });

  test("sorts by title ascending", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string }[];
    }>(
      page,
      `/projects/${pid}/findings?sort=title&order=asc&limit=10`
    );

    expect(response.items.length).toBeGreaterThan(1);
    for (let i = 1; i < response.items.length; i++) {
      const prev = response.items[i - 1].title.toLowerCase();
      const curr = response.items[i].title.toLowerCase();
      expect(prev <= curr).toBe(true);
    }
  });
  test("searches for sql keyword", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.searchFindings("sql");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string; description: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent("sql")}&limit=50`
    );

    expect(response.total).toBeGreaterThan(0);
    for (const f of response.items) {
      const text = `${f.title} ${f.description ?? ""}`.toLowerCase();
      expect(text).toContain("sql");
    }
  });

  test("searches with no results", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.searchFindings("zzz_nonexistent_zzz");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(
        "zzz_nonexistent_zzz"
      )}&limit=1`
    );

    expect(response.total).toBe(0);
  });

  test("clears search", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.searchFindings("sql");
    await page.waitForTimeout(300);
    await findingsPage.clearSearch();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );

    expect(response.total).toBeGreaterThan(0);
  });
  test("creates manual finding with critical severity", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.openCreateFindingModal();
    const title = `E2E Critical Finding ${Date.now()}`;
    testFindingTitles["critical"] = title;
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("critical");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string; severity: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(response.total).toBe(1);
    expect(response.items[0].severity).toBe("critical");
  });

  test("creates manual finding with high severity", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.openCreateFindingModal();
    const title = `E2E High Finding ${Date.now()}`;
    testFindingTitles["high"] = title;
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("high");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string; severity: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(response.total).toBe(1);
    expect(response.items[0].severity).toBe("high");
  });

  test("creates manual finding with medium severity", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.openCreateFindingModal();
    const title = `E2E Medium Finding ${Date.now()}`;
    testFindingTitles["medium"] = title;
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("medium");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string; severity: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(response.total).toBe(1);
    expect(response.items[0].severity).toBe("medium");
  });

  test("creates manual finding with low severity", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.openCreateFindingModal();
    const title = `E2E Low Finding ${Date.now()}`;
    testFindingTitles["low"] = title;
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("low");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string; severity: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(response.total).toBe(1);
    expect(response.items[0].severity).toBe("low");
  });
  test("marks a finding as fixed", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const list = await apiGet<{ items: { id: number }[] }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );
    const findingId = list.items[0].id;

    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.markFixed();
    await page.waitForTimeout(500);

    const response = await apiGet<{ status: string }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );
    expect(response.status).toBe("fixed");
  });

  test("marks a finding as false positive", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const list = await apiGet<{ items: { id: number }[] }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );
    const findingId = list.items[0].id;

    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.markFalsePositive();
    await page.waitForTimeout(500);

    const response = await apiGet<{ status: string }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );
    expect(response.status).toBe("false_positive");
  });

  test("reverts finding status to active", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const list = await apiGet<{ items: { id: number }[] }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );
    const findingId = list.items[0].id;

    await apiPatch(
      page,
      `/projects/${pid}/findings/${findingId}`,
      { status: "active" }
    );

    const response = await apiGet<{ status: string }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );
    expect(response.status).toBe("active");
  });
  test("edits finding title", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const list = await apiGet<{ items: { id: number }[] }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );
    const findingId = list.items[0].id;

    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();

    const newTitle = `E2E Edited Title ${Date.now()}`;
    await findingsPage.editTitle(newTitle);
    await page.waitForTimeout(800);

    const response = await apiGet<{ title: string }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );
    expect(response.title).toBe(newTitle);
  });

  test("toggles should_report flag", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const list = await apiGet<{
      items: { id: number; should_report: boolean }[];
    }>(page, `/projects/${pid}/findings?limit=1`);
    const findingId = list.items[0].id;
    const wasFlagged = list.items[0].should_report;

    await apiPatch(
      page,
      `/projects/${pid}/findings/${findingId}`,
      { should_report: !wasFlagged }
    );

    const response = await apiGet<{ should_report: boolean }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );
    expect(response.should_report).toBe(!wasFlagged);
  });

  test("edits business impact", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const list = await apiGet<{ items: { id: number }[] }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );
    const findingId = list.items[0].id;

    const impact = `E2E Business Impact ${Date.now()}`;
    await apiPatch(
      page,
      `/projects/${pid}/findings/${findingId}`,
      { business_impact: impact }
    );

    const response = await apiGet<{ business_impact: string }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );
    expect(response.business_impact).toContain(impact);
  });
  test("deletes a manual finding", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    const title = `E2E Delete Test ${Date.now()}`;

    await findingsPage.openCreateFindingModal();
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("low");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const findResponse = await apiGet<{
      items: { id: number }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(findResponse.total).toBe(1);
    const findingId = findResponse.items[0].id;

    await findingsPage.searchFindings(title);
    await page.waitForTimeout(500);
    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.deleteFinding();
    await page.waitForTimeout(300);
    await findingsPage.confirmDelete();
    await page.waitForTimeout(1000);

    const verifyResponse = await apiGet<{ items: []; total: number }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(verifyResponse.total).toBe(0);
  });

  test("verifies deleted finding stays deleted after reload", async ({
    findingsPage,
    page,
  }) => {
    const title = `E2E Delete Persist ${Date.now()}`;
    await findingsPage.goto();

    await findingsPage.openCreateFindingModal();
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("low");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const findResponse = await apiGet<{
      items: { id: number }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    const findingId = findResponse.items[0].id;

    await findingsPage.searchFindings(title);
    await page.waitForTimeout(500);
    await findingsPage.clickFindingRow(0);
    await findingsPage.deleteFinding();
    await findingsPage.confirmDelete();
    await page.waitForTimeout(800);

    await page.reload();
    await page.waitForTimeout(1000);

    const verifyResponse = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(verifyResponse.total).toBe(0);
  });

  test("verifies finding count decreased after deletion", async ({
    findingsPage,
    page,
  }) => {
    const title = `E2E Count Test ${Date.now()}`;
    await findingsPage.goto();

    const pid = await getProjectId(page);
    const beforeCount = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );

    await findingsPage.openCreateFindingModal();
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("low");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const afterCreateResponse = await apiGet<{
      items: { id: number }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    const findingId = afterCreateResponse.items[0].id;

    await findingsPage.searchFindings(title);
    await page.waitForTimeout(500);
    await findingsPage.clickFindingRow(0);
    await findingsPage.deleteFinding();
    await findingsPage.confirmDelete();
    await page.waitForTimeout(800);

    const afterDelete = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?limit=1`
    );

    expect(afterDelete.total).toBeLessThanOrEqual(beforeCount.total + 1);
  });
  test("verifies manual finding survives page reload", async ({
    findingsPage,
    page,
  }) => {
    const title = `E2E Reload Persist ${Date.now()}`;
    await findingsPage.goto();

    await findingsPage.openCreateFindingModal();
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("medium");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const findResponse = await apiGet<{
      items: { title: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(findResponse.total).toBe(1);

    await page.reload();
    await page.waitForTimeout(1000);

    await findingsPage.searchFindings(title);
    await page.waitForTimeout(500);

    const reloadResponse = await apiGet<{ total: number }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(reloadResponse.total).toBe(1);
  });

  test("verifies status change survives reload", async ({
    findingsPage,
    page,
  }) => {
    const title = `E2E Status Reload ${Date.now()}`;
    await findingsPage.goto();

    await findingsPage.openCreateFindingModal();
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("high");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const findResponse = await apiGet<{
      items: { id: number }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    const findingId = findResponse.items[0].id;

    await findingsPage.searchFindings(title);
    await page.waitForTimeout(500);
    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.markFixed();
    await page.waitForTimeout(800);

    await page.reload();
    await page.waitForTimeout(1000);

    const statusResponse = await apiGet<{ status: string }>(
      page,
      `/projects/${pid}/findings/${findingId}`
    );

    expect(statusResponse.status).toBe("fixed");
  });
  test("creates manual finding with informational severity", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.openCreateFindingModal();
    const title = `E2E Info Finding ${Date.now()}`;
    await findingsPage.fillManualFindingTitle(title);
    await findingsPage.selectManualFindingSeverity("informational");
    await findingsPage.fillManualFindingUrl("http://test.example.com");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { title: string; severity: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?search=${encodeURIComponent(title)}&limit=1`
    );

    expect(response.total).toBe(1);
    expect(response.items[0].severity).toBe("informational");
  });
  test("filters by severity and tool together", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<{
      items: { severity: string; tool: string }[];
      total: number;
    }>(
      page,
      `/projects/${pid}/findings?severity=high&tool=semgrep&limit=50`
    );

    for (const f of response.items) {
      expect(f.severity).toBe("high");
      expect(f.tool).toBe("semgrep");
    }
  });
});
