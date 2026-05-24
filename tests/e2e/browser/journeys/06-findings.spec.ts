import { test, expect } from "../fixtures/base";

test.describe.serial("Journey 6: Findings Review", () => {
  test("navigates to findings and verifies list", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await expect(page).toHaveURL(/\/findings/);
    await findingsPage.expectFindingsVisible();
  });

  test("clicks a finding and opens detail panel", async ({
    findingsPage,
  }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
  });

  test("edits finding title", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.editTitle("E2E Edited Title");
    await page.waitForTimeout(500);
  });

  test("marks finding as fixed", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.markFixed();
    await page.waitForTimeout(500);
  });

  test("filters by severity", async ({ findingsPage }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.toggleSeverityFilter("critical");
  });

  test("searches findings", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.expectFindingsVisible();
    await findingsPage.searchFindings("sql");
    await page.waitForTimeout(500);
  });

  test("clears search", async ({ findingsPage, page }) => {
    await findingsPage.goto();
    await findingsPage.searchFindings("sql");
    await page.waitForTimeout(500);
    await findingsPage.clearSearch();
    await page.waitForTimeout(500);
    await findingsPage.expectFindingsVisible();
  });

  test("creates a manual finding", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.openCreateFindingModal();
    await findingsPage.fillManualFindingTitle("E2E Manual Finding");
    await findingsPage.selectManualFindingSeverity("high");
    await findingsPage.submitManualFinding();
    await page.waitForTimeout(500);
  });

  test("verifies manual finding in list", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.searchFindings("E2E Manual");
    await page.waitForTimeout(500);
    await expect(
      page.getByText("E2E Manual Finding", { exact: false })
    ).toBeVisible();
  });

  test("deletes the manual finding", async ({
    findingsPage,
    page,
  }) => {
    await findingsPage.goto();
    await findingsPage.searchFindings("E2E Manual");
    await page.waitForTimeout(500);
    await findingsPage.clickFindingRow(0);
    await findingsPage.expectDetailPanelVisible();
    await findingsPage.deleteFinding();
    await findingsPage.confirmDelete();
    await page.waitForTimeout(500);
  });
});
