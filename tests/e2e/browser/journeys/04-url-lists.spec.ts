import { test, expect } from "../fixtures/base";
import { API_DIRECT, TIMEOUTS } from "../fixtures/constants";

test.describe.serial("Journey 4: DAST Scanning", () => {
  test("starts scan with web domain tools", async ({ scansPage }) => {
    test.setTimeout(TIMEOUTS.scan);
    await scansPage.goto();
    await scansPage.openAdvancedOptions();
    await scansPage.selectDomain("web");
    await scansPage.startScan();
    await scansPage.waitForScanComplete();
  });

  test("verifies web scan in history", async ({ scansPage }) => {
    await scansPage.goto();
    await scansPage.switchToHistoryTab();
    await scansPage.expectScanStatus("done");
  });

  test("verifies DAST findings via API", async ({ page }) => {
    const projectsRes = await page.request.get(
      `${API_DIRECT}/projects`
    );
    const projectsBody = await projectsRes.json();
    const projectId = projectsBody.items
      ? projectsBody.items[0].id
      : projectsBody[0].id;

    const findingsRes = await page.request.get(
      `${API_DIRECT}/projects/${projectId}/findings?domain=web&limit=1`
    );
    const findingsBody = await findingsRes.json();
    expect(findingsBody.total).toBeGreaterThan(0);
  });

  test("verifies URL list has entries", async ({ urlListsPage }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.expectUrlCount(1);
  });
});
