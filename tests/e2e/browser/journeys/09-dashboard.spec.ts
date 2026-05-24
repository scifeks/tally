import { test, expect } from "../fixtures/base";

test.describe.serial("Journey 9: Dashboard Verification", () => {
  test("displays project name", async ({ dashboardPage }) => {
    await dashboardPage.goto();
    await dashboardPage.expectProjectName("e2e-test");
  });

  test("shows repository count", async ({ dashboardPage }) => {
    await dashboardPage.goto();
    await dashboardPage.expectStatTile("repositories", 1);
  });

  test("shows recent scans section", async ({
    dashboardPage,
    page,
  }) => {
    await dashboardPage.goto();
    await expect(
      page.getByText("RECENT SCANS", { exact: false })
    ).toBeVisible();
  });

  test("navigates via quick action tiles", async ({
    dashboardPage,
    page,
  }) => {
    await dashboardPage.goto();
    await dashboardPage.clickQuickAction("new scan");
    await expect(page).toHaveURL(/\/scans/);
  });

  test("returns to dashboard and verifies state", async ({
    dashboardPage,
    page,
  }) => {
    await dashboardPage.goto();
    await expect(page).toHaveURL(/\/$/);
    await dashboardPage.expectNotEmpty();
  });
});
