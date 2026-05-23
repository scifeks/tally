import { test, expect } from "../fixtures/base";
import { TEST_REPOS } from "../fixtures/constants";

test.describe.serial("Journey 1: Project Setup", () => {
  test("shows no-project-selected state on fresh load", async ({
    page,
    topBar,
  }) => {
    await page.goto("/");
    await expect(topBar.isNoProjectSelected()).resolves.toBe(true);
    await expect(
      page.getByText("select project", { exact: false })
    ).toBeVisible();
  });

  test("selects the seeded project via the project switcher", async ({
    page,
    topBar,
  }) => {
    await page.goto("/");
    await topBar.selectProject("e2e-test");
    await page.waitForTimeout(1000);
    const name = await topBar.getSelectedProjectName();
    expect(name).toContain("e2e-test");
  });

  test("navigates to Config page", async ({ page, topBar }) => {
    await page.goto("/");
    await topBar.navigateTo("CONFIG");
    await expect(page).toHaveURL(/\/config/);
    await expect(page.getByText("E2E", { exact: false })).toBeVisible();
  });

  test("adds DVWA repository", async ({ configPage }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.dvwa);
    await configPage.expectRepoInList("DVWA");
  });

  test("adds DVPWA repository", async ({ configPage }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.dvpwa);
    await configPage.expectRepoInList("DVPWA");
  });

  test("adds php-goof repository", async ({ configPage }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.phpGoof);
    await configPage.expectRepoInList("php-goof");
  });

  test("adds DVEca repository", async ({ configPage }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.dveca);
    await configPage.expectRepoInList("DVEca");
  });

  test("verifies all 4 repos appear in Config page list", async ({
    configPage,
  }) => {
    await configPage.goto();
    await configPage.expectRepoCount(4);
    await configPage.expectRepoInList("DVWA");
    await configPage.expectRepoInList("DVPWA");
    await configPage.expectRepoInList("php-goof");
    await configPage.expectRepoInList("DVEca");
  });

  test("edits a repository setting and verifies persistence", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await configPage.selectRepoByName("DVWA");
    await page.waitForTimeout(500);

    const nameInput = page.locator("#repo-name");
    await nameInput.fill("DVWA-edited");
    await configPage.clickSave();
    await page.waitForTimeout(500);

    await configPage.expectRepoInList("DVWA-edited");

    await configPage.selectRepoByName("DVWA-edited");
    await page.waitForTimeout(500);
    const currentName = await nameInput.inputValue();
    expect(currentName).toBe("DVWA-edited");

    await nameInput.fill("DVWA");
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
    await configPage.clickDelete();
    await page.waitForTimeout(500);
    await configPage.expectRepoNotInList("DVEca");
    await configPage.expectRepoCount(3);
  });

  test("re-adds the deleted repository", async ({ configPage }) => {
    await configPage.goto();
    await configPage.addRepository(TEST_REPOS.dveca);
    await configPage.expectRepoInList("DVEca");
    await configPage.expectRepoCount(4);
  });
});
