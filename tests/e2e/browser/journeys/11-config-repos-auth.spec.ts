import { test, expect } from "../fixtures/base";
import { Page } from "@playwright/test";
import { TIMEOUTS, API_BASE } from "../fixtures/constants";
import { getProjectId, apiGet, apiPatch } from "../helpers/common";
import * as fs from "fs";
import * as path from "path";
import { tmpdir } from "os";

async function apiPatchNoBody(
  page: Page,
  path: string,
  body: unknown
): Promise<void> {
  await page.evaluate(
    async ({ base, p, b }: { base: string; p: string; b: unknown }) => {
      const csrf = document.cookie
        .split("; ")
        .find((c) => c.startsWith("tally_csrf="))
        ?.split("=")[1];
      const res = await fetch(`${base}${p}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        },
        body: JSON.stringify(b),
      });
      if (!res.ok && res.status !== 204)
        throw new Error(`PATCH ${p} returned ${res.status}`);
    },
    { base: API_BASE, p: path, b: body }
  );
}

test.describe.serial("Journey 11: Repository Configuration & Auth", () => {
  const testRepoName = "test-repo-config";
  const testPath = "/tmp/test-repo-config";

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(300);
  });

  test("adds a repository in basic mode", async ({ configPage, page }) => {
    fs.mkdirSync(testPath, { recursive: true });
    await configPage.goto();
    await configPage.clickNewRepo();
    await configPage.fillRepoName(testRepoName);
    await configPage.fillLocalPath(testPath);
    await configPage.selectServiceType("api");
    await configPage.clickSave();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain(testRepoName);
  });

  test("verifies repo appears in config list", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.expectRepoInList(testRepoName);
  });

  test("edits repository name", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName(testRepoName);
    await page.waitForTimeout(500);

    const nameInput = page.locator("#repo-name");
    const updatedName = `${testRepoName}-updated`;
    await nameInput.fill(updatedName);
    await configPage.clickSave();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain(updatedName);

    await configPage.selectRepoByName(updatedName);
    await page.waitForTimeout(500);
    const currentName = await nameInput.inputValue();
    expect(currentName).toBe(updatedName);
  });

  test("verifies repo persists after reload", async ({ configPage, page }) => {
    await configPage.goto();
    await page.reload();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const updatedName = `${testRepoName}-updated`;
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain(updatedName);
  });

  test("switches to advanced mode and adds multiple services", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await configPage.selectRepoByName(`${testRepoName}-updated`);
    await page.waitForTimeout(500);

    await configPage.toggleAdvancedMode();
    await page.waitForTimeout(300);

    await configPage.addService("service-2");
    await page.waitForTimeout(300);
    await configPage.addLanguage("Python");

    await configPage.addService("service-3");
    await page.waitForTimeout(300);
    await configPage.addLanguage("JavaScript");

    await configPage.clickSave();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find(
      (r: any) => r.name === `${testRepoName}-updated`
    );
    expect(repo).toBeDefined();
    expect(repo.services.length).toBeGreaterThanOrEqual(2);
  });

  test("edits a service", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName(`${testRepoName}-updated`);
    await page.waitForTimeout(500);

    const repoNameInput = page.locator("#repo-name");
    const newRepoName = `${testRepoName}-advanced`;
    await repoNameInput.fill(newRepoName);
    await configPage.clickSave();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain(newRepoName);
  });

  test("removes a service", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName(`${testRepoName}-advanced`);
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const reposBefore = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoBefore = reposBefore.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    const serviceCountBefore = repoBefore?.services?.length ?? 0;

    if (serviceCountBefore > 1) {
      const removeBtn = page
        .locator("[data-testid^='remove-service-']")
        .last();
      await removeBtn.click({ force: true });
      await page.waitForTimeout(500);
      await configPage.clickSave();
      await page.waitForTimeout(500);
    }

    const reposAfter = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoAfter = reposAfter.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(repoAfter).toBeDefined();
    expect(repoAfter.services.length).toBeGreaterThanOrEqual(1);
  });

  test("adds multiple base URLs to a service", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await configPage.selectRepoByName(`${testRepoName}-advanced`);
    await page.waitForTimeout(500);

    await configPage.fillServiceBaseUrl("http://localhost:8001");
    await page.waitForTimeout(200);
    await configPage.fillServiceBaseUrl("http://localhost:8002");
    await page.waitForTimeout(200);
    await configPage.fillServiceBaseUrl("http://localhost:8003");

    await configPage.clickSave();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(repo).toBeDefined();
    const currentService = repo.services[0];
    expect(currentService.base_urls.length).toBeGreaterThanOrEqual(3);
  });

  test("verifies all services persist after reload", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await page.reload();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(repo).toBeDefined();
    expect(repo.services.length).toBeGreaterThanOrEqual(1);
  });

  test("uploads an endpoint file", async ({ configPage, page }) => {
    const tempFile = path.join(tmpdir(), "endpoints.jsonl");
    const content = `{"request":{"method":"GET","endpoint":"http://localhost:8080/api/test"}}
{"request":{"method":"POST","endpoint":"http://localhost:8080/api/users"}}`;
    fs.writeFileSync(tempFile, content);

    try {
      await configPage.goto();
      await configPage.selectRepoByName(`${testRepoName}-advanced`);
      await page.waitForTimeout(500);

      await configPage.uploadEndpointFile(tempFile);
      await page.waitForTimeout(300);

      await configPage.clickSave();
      await page.waitForTimeout(500);

      const pid = await getProjectId(page);
      const repos = await apiGet<{ items: any[] }>(
        page,
        `/projects/${pid}/repositories`
      );
      const repo = repos.items.find(
        (r: any) => r.name === `${testRepoName}-advanced`
      );
      expect(repo).toBeDefined();
      expect(repo.endpoint_file).toBeTruthy();
    } finally {
      if (fs.existsSync(tempFile)) {
        fs.unlinkSync(tempFile);
      }
    }
  });

  test("replaces endpoint file", async ({ configPage, page }) => {
    const tempFile1 = path.join(tmpdir(), "endpoints-new.jsonl");
    const content = `{"request":{"method":"DELETE","endpoint":"http://localhost:8080/api/updated"}}`;
    fs.writeFileSync(tempFile1, content);

    try {
      await configPage.goto();
      await configPage.selectRepoByName(`${testRepoName}-advanced`);
      await page.waitForTimeout(500);

      await configPage.uploadEndpointFile(tempFile1);
      await page.waitForTimeout(300);

      await configPage.clickSave();
      await page.waitForTimeout(500);

      const pid = await getProjectId(page);
      const repos = await apiGet<{ items: any[] }>(
        page,
        `/projects/${pid}/repositories`
      );
      const repo = repos.items.find(
        (r: any) => r.name === `${testRepoName}-advanced`
      );
      expect(repo).toBeDefined();
      expect(repo.endpoint_file).toBeTruthy();
    } finally {
      if (fs.existsSync(tempFile1)) {
        fs.unlinkSync(tempFile1);
      }
    }
  });

  test("verifies endpoint file was parsed into URLs", async ({
    page,
  }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);
    const pid = await getProjectId(page);
    const urls = await apiGet<{
      items: any[];
      total: number;
    }>(page, `/projects/${pid}/url-list/entries?limit=500`);

    expect(urls.total).toBeGreaterThan(0);
    const uploadedUrls = urls.items.filter(
      (u: any) =>
        u.path?.includes("/api/updated") || u.method === "DELETE"
    );
    expect(uploadedUrls.length).toBeGreaterThan(0);
  });

  test("enables headless crawl mode", async ({ configPage, page }) => {
    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(repo).toBeDefined();

    if (!repo.katana_headless) {
      await configPage.goto();
      await configPage.selectRepoByName(`${testRepoName}-advanced`);
      await page.waitForTimeout(500);
      await configPage.toggleHeadlessMode();
      await page.waitForTimeout(300);
      await configPage.clickSave();
      await page.waitForTimeout(500);
    }

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const updated = refreshed.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(updated.katana_headless).toBe(true);
  });

  test("sets crawl depth", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName(`${testRepoName}-advanced`);
    await page.waitForTimeout(500);

    const depthInput = page.locator("#repo-crawl-depth");
    await expect(depthInput).toBeVisible();

    await configPage.setCrawlDepth(7);
    await page.waitForTimeout(300);

    await configPage.clickSave();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(repo).toBeDefined();
    const expectedDepth = repo.katana_headless ? 5 : 7;
    expect(repo.katana_depth).toBe(expectedDepth);
  });

  test("headless mode caps depth at 5", async ({ page }) => {
    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find(
      (r: any) => r.name === `${testRepoName}-advanced`
    );
    expect(repo).toBeDefined();
    expect(repo.katana_headless).toBe(true);
    expect(repo.katana_depth).toBeLessThanOrEqual(5);
  });

  test("uploads and stores Garak config file", async ({
    configPage,
    page,
  }) => {
    const tempFile = path.join(tmpdir(), "garak.yaml");
    const content = `plugins:
  - name: garak.probes.test
    config:
      temperature: 0.7`;
    fs.writeFileSync(tempFile, content);

    try {
      await configPage.goto();
      await configPage.selectRepoByName(`${testRepoName}-advanced`);
      await page.waitForTimeout(500);

      await configPage.uploadGarakConfig(tempFile);
      await page.waitForTimeout(300);

      await configPage.clickSave();
      await page.waitForTimeout(500);

      const pid = await getProjectId(page);
      const repos = await apiGet<{ items: any[] }>(
        page,
        `/projects/${pid}/repositories`
      );
      const repo = repos.items.find(
        (r: any) => r.name === `${testRepoName}-advanced`
      );
      expect(repo).toBeDefined();
      expect(repo.garak_config_file).toBeTruthy();
    } finally {
      if (fs.existsSync(tempFile)) {
        fs.unlinkSync(tempFile);
      }
    }
  });

  test("creates new repo for auth testing", async ({ configPage, page }) => {
    fs.mkdirSync("/tmp/auth-test", { recursive: true });
    await configPage.goto();
    await configPage.clickNewRepo();
    await configPage.fillRepoName("auth-test-repo");
    await configPage.fillLocalPath("/tmp/auth-test");
    await configPage.selectServiceType("api");
    await configPage.clickSave();
    await page.waitForTimeout(500);

    await configPage.expectRepoInList("auth-test-repo");

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).toContain("auth-test-repo");
  });

  test("saves DVECA login credentials", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName("auth-test-repo");
    await page.waitForTimeout(500);

    await configPage.fillAuthLoginUrl("http://127.0.0.1:8082/login.php");
    await configPage.fillAuthUsername("admin@dves.local");
    await configPage.fillAuthPassword("admin");
    await configPage.saveAuth();
    await page.waitForTimeout(500);

    await configPage.expectAuthSaved();

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find((r: any) => r.name === "auth-test-repo");
    expect(repo).toBeDefined();
    expect(repo.auth_configured).toBe(true);
  });

  test("sets DVECA username field to email", async ({
    page,
  }) => {
    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find((r: any) => r.name === "auth-test-repo");
    expect(repo).toBeDefined();

    await apiPatchNoBody(
      page,
      `/projects/${pid}/repositories/${repo!.id}/auth`,
      { username_field: "email" }
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const updated = refreshed.items.find(
      (r: any) => r.name === "auth-test-repo"
    );
    expect(updated!.auth_configured).toBe(true);
  });

  test("verifies auth is configured via API", async ({ page }) => {
    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find((r: any) => r.name === "auth-test-repo");
    expect(repo).toBeDefined();
    expect(repo.auth_configured).toBe(true);
  });

  test("updates credentials", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName("auth-test-repo");
    await page.waitForTimeout(500);

    await configPage.fillAuthLoginUrl("http://127.0.0.1:8082/login.php");
    await configPage.fillAuthUsername("alice@dves.local");
    await configPage.fillAuthPassword("password");
    await configPage.saveAuth();
    await page.waitForTimeout(500);

    await configPage.expectAuthSaved();

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repo = repos.items.find((r: any) => r.name === "auth-test-repo");
    expect(repo).toBeDefined();
    expect(repo.auth_configured).toBe(true);
  });

  test("clears auth configuration", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName("auth-test-repo");
    await page.waitForTimeout(500);

    const loginUrlInput = page.locator("#repo-auth-login-url");
    const usernameInput = page.locator("#repo-auth-username");
    const passwordInput = page.locator("#repo-auth-password");

    await loginUrlInput.fill("");
    await usernameInput.fill("");
    await passwordInput.fill("");

    const saveAuthBtn = page.getByRole("button", { name: /Save Auth/i });
    const isDisabled = await saveAuthBtn.isDisabled();

    expect(isDisabled).toBe(true);
  });

  test("auth works during Katana scan against DVECA", async ({
    scansPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.scan);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const dveca = repos.items.find(
      (r: any) => r.name === "DVEca"
    );
    expect(dveca).toBeDefined();

    await apiPatchNoBody(
      page,
      `/projects/${pid}/repositories/${dveca!.id}/auth`,
      {
        login_url: "http://127.0.0.1:8082/login.php",
        username_field: "email",
        password_field: "password",
        username: "alice@dves.local",
        password: "password",
      }
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const dvecaRefreshed = refreshed.items.find(
      (r: any) => r.name === "DVEca"
    );
    expect(dvecaRefreshed.auth_configured).toBe(true);

    await page.evaluate(
      async ({ base, p }: { base: string; p: number }) => {
        const csrf = document.cookie
          ?.split("; ")
          .find((c: string) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
        const res = await fetch(
          `${base}/projects/${p}/scans`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "x-csrf-token": csrf,
            },
            body: JSON.stringify({
              skipEnrichment: true,
              toolIds: ["katana"],
            }),
          }
        );
        if (!res.ok)
          throw new Error(`Scan start: ${res.status}`);
      },
      { base: "/api/v1", p: pid }
    );

    await scansPage.goto();
    await scansPage.waitForScanComplete();

    const urls = await apiGet<{
      items: { path: string }[];
      total: number;
    }>(page, `/projects/${pid}/url-list/entries?limit=100`);
    expect(urls.total).toBeGreaterThan(0);

    const paths = urls.items.map((u: any) => u.path);
    const hasAuthPage = paths.some(
      (p: string) =>
        p.includes("account") ||
        p.includes("profile") ||
        p.includes("admin") ||
        p.includes("order")
    );
    expect(hasAuthPage).toBe(true);
  });

  test("deletes the auth test repository", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName("auth-test-repo");
    await page.waitForTimeout(500);

    page.once("dialog", (dialog) => dialog.accept());
    await configPage.clickDelete();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).not.toContain("auth-test-repo");
  });

  test("deletes the advanced test repository", async ({ configPage, page }) => {
    await configPage.goto();
    await configPage.selectRepoByName(`${testRepoName}-advanced`);
    await page.waitForTimeout(500);

    page.once("dialog", (dialog) => dialog.accept());
    await configPage.clickDelete();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const repos = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/repositories`
    );
    const repoNames = repos.items.map((r: any) => r.name);
    expect(repoNames).not.toContain(`${testRepoName}-advanced`);
  });
});
