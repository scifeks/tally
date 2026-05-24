import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";

test.describe.serial("Journey 7: Reporting", () => {
  test("navigates to reports page", async ({
    reportsPage,
    page,
  }) => {
    await reportsPage.goto();
    await expect(page).toHaveURL(/\/reports/);
  });

  test("generates an executive summary draft", async ({
    reportsPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.reportGeneration);
    await reportsPage.goto();
    await reportsPage.generateDraftSection("executive-summary");
    await expect(
      page.getByText(/draft ready/i)
    ).toBeVisible({ timeout: TIMEOUTS.reportGeneration });
  });

  test("fills report metadata", async ({ reportsPage }) => {
    await reportsPage.goto();
    await reportsPage.selectFormat("pdf");
    await reportsPage.fillCompanyName("E2E Test Corp");
    await reportsPage.fillEngagementDate("2026-05-23");
  });

  test("generates full report", async ({ reportsPage, page }) => {
    test.setTimeout(TIMEOUTS.reportGeneration);
    await reportsPage.goto();
    await reportsPage.selectFormat("pdf");
    await reportsPage.fillCompanyName("E2E Test Corp");
    await reportsPage.clickGenerateReport();
    await expect(
      page.getByText(/completed|done/i)
    ).toBeVisible({ timeout: TIMEOUTS.reportGeneration });
  });

  test("verifies report in history", async ({
    reportsPage,
    page,
  }) => {
    await reportsPage.goto();
    await reportsPage.switchToHistoryTab();
    await page.waitForTimeout(500);
    await expect(page.getByText(/\.pdf/i)).toBeVisible();
  });
});
