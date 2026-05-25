import { test, expect } from "../fixtures/base";
import { NAV_TABS } from "../fixtures/constants";

test.describe.serial("Journey 10: Cross-Cutting Concerns", () => {
  test("navigates to each tab via top bar", async ({
    topBar,
    page,
  }) => {
    await page.goto("/");

    const expectedUrls: Record<string, RegExp> = {
      DASHBOARD: /\/$/,
      FINDINGS: /\/findings/,
      "URL LISTS": /\/urls/,
      SCANS: /\/scans/,
      REPORTS: /\/reports/,
      CHAT: /\/chat/,
      CONFIG: /\/config/,
    };

    for (const tab of NAV_TABS) {
      if (tab === "TRIAGE") continue;
      await topBar.navigateTo(tab);
      await expect(page).toHaveURL(expectedUrls[tab]);
    }
  });

  test("verifies CONFIG routes to /config", async ({
    topBar,
    page,
  }) => {
    await page.goto("/");
    await topBar.navigateTo("CONFIG");
    await expect(page).toHaveURL(/\/config/);
  });

  test("verifies FINDINGS routes to /findings", async ({
    topBar,
    page,
  }) => {
    await page.goto("/");
    await topBar.navigateTo("FINDINGS");
    await expect(page).toHaveURL(/\/findings/);
  });

  test("verifies SCANS routes to /scans", async ({
    topBar,
    page,
  }) => {
    await page.goto("/");
    await topBar.navigateTo("SCANS");
    await expect(page).toHaveURL(/\/scans/);
  });

  test("verifies project switcher shows project", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: /e2e/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("direct URL navigation works", async ({ page }) => {
    await page.goto("/findings");
    await expect(page).toHaveURL(/\/findings/);

    await page.goto("/config");
    await expect(page).toHaveURL(/\/config/);

    await page.goto("/scans");
    await expect(page).toHaveURL(/\/scans/);
  });

  test("browser back button navigates correctly", async ({
    page,
  }) => {
    await page.goto("/");
    await page.goto("/findings");
    await page.goto("/scans");
    await page.goBack();
    await expect(page).toHaveURL(/\/findings/);
    await page.goBack();
    await expect(page).toHaveURL(/\/$/);
  });
});
