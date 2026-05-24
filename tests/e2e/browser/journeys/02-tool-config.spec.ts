import { test, expect } from "../fixtures/base";
import {
  API_BASE,
  DVECA_SCAN_TARGET_SERVICES,
  buildScaOverrides,
} from "../fixtures/constants";
import { TallyApi } from "../helpers/api";

test.describe.serial("Journey 2: Tool Configuration", () => {
  test("verifies tool catalog is populated", async ({ page }) => {
    await page.goto("/");
    const catalogBody = await page.evaluate(async () => {
      const res = await fetch("/api/v1/tools/catalog");
      return res.json();
    });
    const tools = Array.isArray(catalogBody)
      ? catalogBody
      : catalogBody.items ?? [];
    expect(tools.length).toBeGreaterThan(0);
  });

  test("adds and saves a tool override", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await page.waitForTimeout(500);

    const addSelect = page.locator("select").last();
    await addSelect.waitFor({ state: "visible" });
    await addSelect.selectOption({ index: 1 });
    await page.waitForTimeout(1000);

    const toolPathInput = page.locator("#tool-path");
    if (await toolPathInput.isVisible()) {
      await toolPathInput.fill("/usr/local/bin/tool");
    }

    const saveBtn = page
      .getByRole("button", { name: /Save|Create/i })
      .last();
    await saveBtn.scrollIntoViewIfNeeded();
    await expect(saveBtn).toBeEnabled({ timeout: 5000 });
    await saveBtn.click();
    await page.waitForTimeout(1000);
  });

  test("verifies override persists after reload", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await page.waitForTimeout(1000);
    const overrideSelect = page.locator("select").nth(1);
    const optionCount = await overrideSelect
      .locator("option")
      .count();
    expect(optionCount).toBeGreaterThanOrEqual(1);
  });

  test("deletes the tool override", async ({
    configPage,
    page,
  }) => {
    await configPage.goto();
    await page.waitForTimeout(1000);
    const overrideSelect = page.locator("select").nth(1);
    await overrideSelect.selectOption({ index: 1 });
    await page.waitForTimeout(1000);

    const removeBtn = page.getByRole("button", {
      name: /Remove|Delete/i,
    });
    await removeBtn.scrollIntoViewIfNeeded();
    page.once("dialog", (dialog) => dialog.accept());
    await removeBtn.click();
    await page.waitForTimeout(1000);

    await configPage.goto();
    await page.waitForTimeout(1000);
    await expect(
      page.getByText("No tool overrides configured", {
        exact: false,
      })
        .or(
          page.getByText("Select a tool override", {
            exact: false,
          })
        )
    ).toBeVisible({ timeout: 5000 });
  });
});

test.describe.serial("Journey 2b: DVEca Scan-Target Configuration", () => {
  let projectId: number;
  let dvecaRepoId: number;

  test("looks up DVEca repo ID", async ({ request }) => {
    const api = new TallyApi(request);
    const { items: projects } = await api.listProjects();
    projectId = projects[0].id;

    const repos = await api.getRepositories(projectId);
    const dveca = repos.find((r) => r.name === "DVEca");
    expect(dveca).toBeDefined();
    dvecaRepoId = dveca!.id;
  });

  test("adds scan-target services to DVEca repo", async ({
    request,
  }) => {
    const api = new TallyApi(request);
    const repos = await api.getRepositories(projectId);
    const dveca = repos.find((r) => r.name === "DVEca");

    const existingServices = (dveca as unknown as Record<string, unknown>)
      .services as Record<string, unknown>[];
    const merged = [
      ...(existingServices ?? []),
      ...DVECA_SCAN_TARGET_SERVICES,
    ];

    await api.patchRepository(projectId, dvecaRepoId, {
      services: merged,
    });
  });

  test("creates service-scoped tool overrides for SCA", async ({
    request,
  }) => {
    const api = new TallyApi(request);
    const overrides = buildScaOverrides(dvecaRepoId);

    for (const override of overrides) {
      const result = await api.createToolOverride(
        projectId,
        override
      );
      expect(result.id).toBeGreaterThan(0);
      expect(result.scope).toBe("service");
    }
  });

  test("verifies all 3 service-scoped overrides exist", async ({
    request,
  }) => {
    const api = new TallyApi(request);
    const { items } = await api.listToolOverrides(projectId);
    const scoped = items.filter((o) => o.scope === "service");
    expect(scoped.length).toBe(3);

    const toolNames = scoped.map((o) => o.toolName).sort();
    expect(toolNames).toEqual([
      "composer-audit",
      "npm-audit",
      "pip-audit",
    ]);
  });
});
