import { test, expect } from "../fixtures/base";
import { TEST_REPOS } from "../fixtures/constants";
import { getProjectId, apiGet } from "../helpers/common";

test.describe.serial("Journey 1: Project Setup", () => {
  test("verifies project is selected from global setup", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("button", { name: /e2e/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("navigates to Config page", async ({ page, topBar }) => {
    await page.goto("/");
    await topBar.navigateTo("CONFIG");
    await expect(page).toHaveURL(/\/config/);
    await expect(page.getByText("E2E", { exact: true }).first()).toBeVisible();
  });

  test("adds DVEca repository", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.dveca);
    await configPage.expectRepoInList("DVEca");

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain("DVEca");
  });

  test("verifies repo appears in Config page list", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await page.waitForTimeout(1000);
    await configPage.expectRepoCount(1);
    await configPage.expectRepoInList("DVEca");
  });

  test("edits a repository setting and verifies persistence", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await configPage.selectRepoByName("DVEca");
    await page.waitForTimeout(500);

    const nameInput = page.locator("#repo-name");
    await nameInput.fill("DVEca-edited");
    await configPage.clickSave();
    await page.waitForTimeout(500);

    await configPage.expectRepoInList("DVEca-edited");

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain("DVEca-edited");

    await configPage.selectRepoByName("DVEca-edited");
    await page.waitForTimeout(500);
    const currentName = await nameInput.inputValue();
    expect(currentName).toBe("DVEca-edited");

    await nameInput.fill("DVEca");
    await configPage.clickSave();
    await page.waitForTimeout(500);
  });

  test("deletes a repository and verifies removal", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await configPage.selectRepoByName("DVEca");
    await page.waitForTimeout(500);
    page.once("dialog", (dialog) => dialog.accept());
    await configPage.clickDelete();
    await page.waitForTimeout(1000);
    await configPage.goto();
    await configPage.expectRepoNotInList("DVEca");
    await configPage.expectRepoCount(0);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    expect(repos.items.length).toBe(0);
  });

  test("re-adds the deleted repository", async ({ configPage }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.dveca);
    await configPage.expectRepoInList("DVEca");
    await configPage.expectRepoCount(1);
  });
});
