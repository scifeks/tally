import { test, expect } from "../fixtures/base";
import {
  API_BASE,
  DVECA_SCAN_TARGET_SERVICES,
  buildScaOverrides,
} from "../fixtures/constants";
import { TallyApi } from "../helpers/api";
import { getProjectId, apiGet } from "../helpers/common";

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
      await toolPathInput.fill("/usr/local/bin/gitleaks");
    }

    const saveBtn = page
      .getByRole("button", { name: /Save|Create/i })
      .last();
    await saveBtn.scrollIntoViewIfNeeded();
    await expect(saveBtn).toBeEnabled({ timeout: 5000 });
    await saveBtn.click();
    await page.waitForTimeout(1000);

    const pid = await getProjectId(page);
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/tools/overrides`
    );
    expect(overrides.items.length).toBeGreaterThan(0);
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

    const pid = await getProjectId(page);
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${pid}/tools/overrides`
    );
    expect(overrides.items.length).toBe(0);
  });
});

test.describe.serial("Journey 2b: DVEca Scan-Target Configuration", () => {
  let projectId: number;
  let dvecaRepoId: number;

  test("looks up DVEca repo ID", async ({ page }) => {
    await page.goto("/");
    const { pid, repoId } = await page.evaluate(async () => {
      const projRes = await fetch("/api/v1/projects");
      const projBody = await projRes.json();
      const projects = projBody.items ?? projBody;
      const pid = projects[0].id;

      const repoRes = await fetch(`/api/v1/projects/${pid}/repositories`);
      const repoBody = await repoRes.json();
      const repos = repoBody.items ?? repoBody;
      const dveca = repos.find((r: { name: string }) => r.name === "DVEca");
      return { pid, repoId: dveca?.id };
    });

    expect(repoId).toBeDefined();
    projectId = pid;
    dvecaRepoId = repoId!;
  });

  test("adds scan-target services to DVEca repo", async ({
    page,
  }) => {
    await page.goto("/");
    const services = DVECA_SCAN_TARGET_SERVICES;
    const res = await page.evaluate(
      async ({ pid, rid, svcs }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
        const repoRes = await fetch(`/api/v1/projects/${pid}/repositories`);
        const repoBody = await repoRes.json();
        const repos = repoBody.items ?? repoBody;
        const dveca = repos.find((r: { name: string }) => r.name === "DVEca");
        const existing = ((dveca as Record<string, unknown>)?.services ?? []) as Array<{name: string}>;
        const existingNames = new Set(existing.map((s: {name: string}) => s.name));
        const newOnly = (svcs as Array<{name: string}>).filter((s) => !existingNames.has(s.name));
        const merged = [...existing, ...newOnly];

        const form = new URLSearchParams();
        form.set("payload", JSON.stringify({ services: merged }));
        const patchRes = await fetch(
          `/api/v1/projects/${pid}/repositories/${rid}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/x-www-form-urlencoded",
              "x-csrf-token": csrf,
            },
            body: form.toString(),
          }
        );
        return patchRes.ok;
      },
      { pid: projectId, rid: dvecaRepoId, svcs: [...services] }
    );
    expect(res).toBe(true);
  });

  test("creates service-scoped tool overrides for SCA", async ({
    page,
  }) => {
    await page.goto("/");
    const overrides = buildScaOverrides(dvecaRepoId);
    const allCreated = await page.evaluate(
      async ({ pid, ovrs }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";

        const results: boolean[] = [];
        for (const ovr of ovrs) {
          const res = await fetch(
            `/api/v1/projects/${pid}/tools/overrides`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "x-csrf-token": csrf,
              },
              body: JSON.stringify(ovr),
            }
          );
          if (!res.ok && res.status !== 409) {
            const err = await res.text();
            throw new Error(
              `Override ${ovr.toolName} failed (${res.status}): ${err}`
            );
          }
          results.push(res.ok || res.status === 409);
        }
        return results.every((r) => r);
      },
      { pid: projectId, ovrs: overrides }
    );
    expect(allCreated).toBe(true);
  });

  test("verifies all 3 service-scoped overrides exist", async ({
    page,
  }) => {
    await page.goto("/");
    const scoped = await page.evaluate(async (pid) => {
      const res = await fetch(`/api/v1/projects/${pid}/tools/overrides`);
      const payload = await res.json();
      const allOverrides = payload.items ?? payload;
      return allOverrides.filter((o: { scope: string }) => o.scope === "service");
    }, projectId);

    const toolNames = [
      ...new Set(
        scoped.map((o: { toolName: string }) => o.toolName)
      ),
    ].sort();
    expect(toolNames).toEqual([
      "composer-audit",
      "npm-audit",
      "pip-audit",
    ]);
  });
});
