import { test, expect } from "../fixtures/base";
import {
  getProjectId,
  apiGet,
  apiPost,
  apiPut,
  apiPatch,
  apiDelete,
} from "../helpers/common";
import { buildScaOverrides, DVECA_SCAN_TARGET_SERVICES } from "../fixtures/constants";

test.describe.serial("Journey 12: Tool Overrides & Argument Profiles", () => {
  let projectId: number;
  let dvecaRepoId: number;

  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("gets project and repo IDs", async ({ page }) => {
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

  test("creates global override with local path", async ({ page }) => {
    await page.goto("/");
    await apiDelete(page, `/projects/${projectId}/tools/overrides/gitleaks`)
      .catch(() => {});
    const override = {
      toolName: "gitleaks",
      type: "repo" as const,
      location: "local" as const,
      path: "/usr/local/bin/gitleaks",
      argsMode: "stock" as const,
    };

    const result = await apiPost(page, `/projects/${projectId}/tools/overrides`, {
      toolName: override.toolName,
      type: override.type,
      location: override.location,
      path: override.path,
      argsMode: override.argsMode,
    });

    expect(result).toBeDefined();

    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const created = overrides.items.find(
      (o: any) => o.toolName === "gitleaks" && o.scope === "global"
    );
    expect(created).toBeDefined();
    expect(created.location).toBe("local");
    expect(created.path).toBe("/usr/local/bin/gitleaks");
  });

  test("creates global override with Docker location", async ({ page }) => {
    await page.goto("/");
    await apiDelete(page, `/projects/${projectId}/tools/overrides/zap`)
      .catch(() => {});
    const override = {
      toolName: "zap",
      type: "repo" as const,
      location: "docker" as const,
      container: {
        name: "zap-container",
        toolPath: "/usr/local/bin/zaproxy",
      },
      argsMode: "stock" as const,
    };

    const result = await apiPost(page, `/projects/${projectId}/tools/overrides`, {
      toolName: override.toolName,
      type: override.type,
      location: override.location,
      container: override.container,
      argsMode: override.argsMode,
    });

    expect(result).toBeDefined();

    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const created = overrides.items.find(
      (o: any) => o.toolName === "zap" && o.scope === "global"
    );
    expect(created).toBeDefined();
    expect(created.location).toBe("docker");
    expect(created.container?.name).toBe("zap-container");
  });

  test("updates override location", async ({ page }) => {
    await page.goto("/");
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const override = overrides.items.find(
      (o: any) => o.toolName === "zap" && o.scope === "global"
    );

    expect(override).toBeDefined();

    const result = await apiPut(
      page,
      `/projects/${projectId}/tools/overrides/${override.toolName}`,
      {
        toolName: override.toolName,
        type: override.type,
        location: "local",
        path: "/usr/local/bin/zaproxy",
        argsMode: override.argsMode,
      }
    );

    expect(result).toBeDefined();

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const updated_override = refreshed.items.find(
      (o: any) => o.toolName === "zap"
    );
    expect(updated_override.location).toBe("local");
  });

  test("deletes global override", async ({ page }) => {
    await page.goto("/");
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const gitleaks = overrides.items.find(
      (o: any) => o.toolName === "gitleaks" && o.scope === "global"
    );

    expect(gitleaks).toBeDefined();

    await apiDelete(page, `/projects/${projectId}/tools/overrides/${gitleaks.toolName}`);

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const deleted = refreshed.items.find(
      (o: any) => o.toolName === "gitleaks" && o.scope === "global"
    );
    expect(deleted).toBeUndefined();
  });

  test("adds scan-target services to DVEca repo", async ({ page }) => {
    await page.goto("/");
    const services = DVECA_SCAN_TARGET_SERVICES;
    await page.evaluate(
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
        if (!patchRes.ok) {
          throw new Error(`Failed to add services: ${patchRes.status}`);
        }
      },
      { pid: projectId, rid: dvecaRepoId, svcs: [...services] }
    );
  });

  test("creates service-scoped override", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const existing = overrides.items.find(
      (o: any) =>
        o.toolName === "composer-audit" &&
        o.scope === "service" &&
        o.serviceName === "sca-php"
    );

    if (!existing) {
      const override = {
        toolName: "composer-audit",
        argsMode: "stock" as const,
        type: "repo" as const,
        location: "docker" as const,
        scope: "service" as const,
        repoId: dvecaRepoId,
        serviceName: "sca-php",
        container: {
          name: "dveca-scan-target-1",
          toolPath: "/usr/local/bin/composer",
        },
      };
      await apiPost(page, `/projects/${projectId}/tools/overrides`, {
        ...override,
      });
    }

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const created = refreshed.items.find(
      (o: any) => o.toolName === "composer-audit" && o.scope === "service"
    );
    expect(created).toBeDefined();
    expect(created.serviceName).toBe("sca-php");
    expect(created.repoId).toBe(dvecaRepoId);
  });

  test("creates multiple service-scoped overrides", async ({ page }) => {
    const overrides = buildScaOverrides(dvecaRepoId);

    await page.evaluate(
      async ({ pid, ovrs }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";

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
        }
      },
      { pid: projectId, ovrs: overrides }
    );

    const allOverrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const scoped = allOverrides.items.filter(
      (o: any) => o.scope === "service" && o.repoId === dvecaRepoId
    );

    expect(scoped.length).toBeGreaterThanOrEqual(3);
  });

  test("deletes one service-scoped override", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const scoped = overrides.items.filter(
      (o: any) => o.scope === "service" && o.repoId === dvecaRepoId
    );
    expect(scoped.length).toBeGreaterThan(0);

    const toDelete = scoped[0];
    await apiDelete(
      page,
      `/projects/${projectId}/tools/overrides/${dvecaRepoId}/${toDelete.serviceName}/${toDelete.toolName}`
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const remaining = refreshed.items.filter(
      (o: any) =>
        o.scope === "service" &&
        o.repoId === dvecaRepoId &&
        o.toolName === toDelete.toolName &&
        o.serviceName === toDelete.serviceName
    );
    expect(remaining.length).toBe(0);
  });

  test("creates argument profile with flag args", async ({ page }) => {
    const existingProfiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    for (const p of existingProfiles.items) {
      await apiDelete(page, `/projects/${projectId}/arg-profiles/${p.id}`)
        .catch(() => {});
    }

    const payload = {
      toolName: "zap",
      name: "ZAP Quick Scan",
      args: [
        { name: "-T", value: "30", type: "string" },
        { name: "-m", value: "2", type: "string" },
      ],
    };

    await page.evaluate(
      async ({ base, pid, body }: {
        base: string; pid: number; body: unknown;
      }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
        const form = new URLSearchParams();
        form.set("payload", JSON.stringify(body));
        const res = await fetch(
          `${base}/projects/${pid}/arg-profiles`,
          {
            method: "POST",
            headers: { "x-csrf-token": csrf },
            body: form,
          }
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`POST arg-profiles: ${res.status} ${text}`);
        }
      },
      { base: "/api/v1", pid: projectId, body: payload }
    );

    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const created = profiles.items.find(
      (p: any) => p.name === "ZAP Quick Scan"
    );
    expect(created).toBeDefined();
    expect(created.args.length).toBe(2);
  });

  test("creates profile with file-type argument", async ({ page }) => {
    const payload = {
      toolName: "gitleaks",
      name: "Gitleaks with Config",
      args: [
        { name: "--config", type: "flag" },
      ],
    };

    await page.evaluate(
      async ({ base, pid, body }: {
        base: string; pid: number; body: unknown;
      }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
        const form = new URLSearchParams();
        form.set("payload", JSON.stringify(body));
        const res = await fetch(
          `${base}/projects/${pid}/arg-profiles`,
          {
            method: "POST",
            headers: { "x-csrf-token": csrf },
            body: form,
          }
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`POST arg-profiles: ${res.status} ${text}`);
        }
      },
      { base: "/api/v1", pid: projectId, body: payload }
    );

    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const created = profiles.items.find(
      (p: any) => p.name === "Gitleaks with Config"
    );
    expect(created).toBeDefined();
  });

  test("edits argument profile", async ({ page }) => {
    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const profile = profiles.items.find(
      (p: any) => p.name === "ZAP Quick Scan"
    );
    expect(profile).toBeDefined();

    const payload = {
      toolName: profile.toolName,
      name: "ZAP Extended Scan",
      args: [
        { name: "-T", value: "60", type: "string" },
        { name: "-m", value: "3", type: "string" },
        { name: "-d", type: "flag" },
      ],
    };

    await page.evaluate(
      async ({ base, pid, profId, body }: {
        base: string; pid: number; profId: number; body: unknown;
      }) => {
        const csrf = document.cookie
          .split("; ")
          .find((c) => c.startsWith("tally_csrf="))
          ?.split("=")[1] ?? "";
        const form = new URLSearchParams();
        form.set("payload", JSON.stringify(body));
        const res = await fetch(
          `${base}/projects/${pid}/arg-profiles/${profId}`,
          {
            method: "PUT",
            headers: { "x-csrf-token": csrf },
            body: form,
          }
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`PUT arg-profiles: ${res.status} ${text}`);
        }
      },
      { base: "/api/v1", pid: projectId, profId: profile.id, body: payload }
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const updated_profile = refreshed.items.find(
      (p: any) => p.id === profile.id
    );
    expect(updated_profile.name).toBe("ZAP Extended Scan");
    expect(updated_profile.args.length).toBe(3);
  });

  test("deletes argument profile", async ({ page }) => {
    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const toDelete = profiles.items.find(
      (p: any) => p.name === "Gitleaks with Config"
    );

    expect(toDelete).toBeDefined();

    await apiDelete(
      page,
      `/projects/${projectId}/arg-profiles/${toDelete.id}`
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const deleted = refreshed.items.find(
      (p: any) => p.id === toDelete.id
    );
    expect(deleted).toBeUndefined();
  });

  test("sets override to custom args mode", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const override = overrides.items.find(
      (o: any) => o.toolName === "zap" && o.scope === "global"
    );
    expect(override).toBeDefined();

    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const profile = profiles.items.find(
      (p: any) => p.name === "ZAP Extended Scan"
    );
    expect(profile).toBeDefined();

    await apiPut(
      page,
      `/projects/${projectId}/tools/overrides/${override.toolName}`,
      {
        toolName: override.toolName,
        type: override.type,
        location: override.location,
        path: override.path,
        argsMode: "custom",
        argProfileId: profile.id,
      }
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const updated_override = refreshed.items.find(
      (o: any) => o.toolName === "zap"
    );
    expect(updated_override.argsMode).toBe("custom");
  });

  test("verifies profile is listed on override", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const override = overrides.items.find(
      (o: any) => o.toolName === "zap" && o.argsMode === "custom"
    );
    expect(override).toBeDefined();

    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    const profile = profiles.items.find(
      (p: any) => p.name === "ZAP Extended Scan"
    );
    expect(profile).toBeDefined();
  });

  test("switches back to stock args", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const override = overrides.items.find(
      (o: any) => o.toolName === "zap" && o.argsMode === "custom"
    );
    expect(override).toBeDefined();

    await apiPut(
      page,
      `/projects/${projectId}/tools/overrides/${override.toolName}`,
      {
        toolName: override.toolName,
        type: override.type,
        location: override.location,
        path: override.path,
        argsMode: "stock",
      }
    );

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const updated_override = refreshed.items.find(
      (o: any) => o.toolName === "zap"
    );
    expect(updated_override.argsMode).toBe("stock");
  });

  test("cleans up tool overrides", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );

    for (const override of overrides.items) {
      if (override.scope === "global") {
        await apiDelete(
          page,
          `/projects/${projectId}/tools/overrides/${override.toolName}`
        );
      }
    }

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const globals = refreshed.items.filter(
      (o: any) => o.scope === "global"
    );
    expect(globals.length).toBe(0);
  });

  test("cleans up argument profiles", async ({ page }) => {
    const profiles = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );

    for (const profile of profiles.items) {
      await apiDelete(
        page,
        `/projects/${projectId}/arg-profiles/${profile.id}`
      );
    }

    const refreshed = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/arg-profiles`
    );
    expect(refreshed.items.length).toBe(0);
  });

  test("override affects actual scan execution", async ({ page }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const scoped = overrides.items.filter(
      (o: any) => o.scope === "service" && o.repoId === dvecaRepoId
    );
    expect(scoped.length).toBeGreaterThan(0);

    const scaOverride = scoped.find(
      (o: any) =>
        o.toolName === "composer-audit" ||
        o.toolName === "npm-audit" ||
        o.toolName === "pip-audit"
    );
    expect(scaOverride).toBeDefined();
    expect(scaOverride.location).toBe("docker");
  });

  test("service-scoped override applies to correct service only", async ({
    page,
  }) => {
    const overrides = await apiGet<{ items: any[] }>(
      page,
      `/projects/${projectId}/tools/overrides`
    );
    const scoped = overrides.items.filter(
      (o: any) => o.scope === "service" && o.repoId === dvecaRepoId
    );

    for (const override of scoped) {
      expect(override.serviceName).toBeTruthy();
      expect(override.repoId).toBe(dvecaRepoId);
    }
  });
});
