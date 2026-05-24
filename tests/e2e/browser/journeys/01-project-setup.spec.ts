import { test, expect } from "../fixtures/base";
import { TEST_REPOS } from "../fixtures/constants";

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
    page,
  }) => {
    await configPage.goto();
    await page.waitForTimeout(1000);
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
    page.once("dialog", (dialog) => dialog.accept());
    await configPage.clickDelete();
    await page.waitForTimeout(1000);
    await configPage.goto();
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
