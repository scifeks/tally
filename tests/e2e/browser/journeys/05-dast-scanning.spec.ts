import { test, expect } from "../fixtures/base";
import { TallyApi } from "../helpers/api";
import path from "path";

test.describe.serial("Journey 5: URL List Discovery", () => {
  test("navigates to URL Lists page", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await expect(page).toHaveURL(/\/urls/);
  });

  test("verifies URLs populated from scans", async ({
    urlListsPage,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.expectUrlCount(1);
  });

  test("searches for a URL path", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.searchUrls("login");
    await page.waitForTimeout(500);
  });

  test("clears search and verifies full list", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.searchUrls("test-query");
    await page.waitForTimeout(500);
    await urlListsPage.clearSearch();
    await page.waitForTimeout(500);
    await urlListsPage.expectUrlsVisible();
  });

  test("filters by method via column header", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("GET");
    await page.waitForTimeout(500);
    await urlListsPage.expectUrlsVisible();
  });

  test("clears all filters", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("GET");
    await page.waitForTimeout(500);
    await urlListsPage.clearFilters();
    await page.waitForTimeout(500);
    await urlListsPage.expectUrlsVisible();
  });

  test("uploads endpoint file and verifies URLs appear", async ({
    request,
    urlListsPage,
    page,
  }) => {
    const api = new TallyApi(request);
    const { items: projects } = await api.listProjects();
    const projectId = projects[0].id;
    const repos = await api.getRepositories(projectId);
    const dveca = repos.find((r) => r.name === "DVEca");
    expect(dveca).toBeDefined();

    const fixturePath = path.resolve(
      __dirname,
      "../fixtures/dveca-endpoints.jsonl"
    );
    await api.uploadEndpointFile(projectId, dveca!.id, fixturePath);

    await urlListsPage.goto();
    await page.waitForTimeout(2000);
    await urlListsPage.expectUrlsVisible();
  });
});
