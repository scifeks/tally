import { Page } from "@playwright/test";
import { API_BASE } from "../fixtures/constants";

export async function getProjectId(page: Page): Promise<number> {
  return page.evaluate(async (base: string) => {
    const res = await fetch(`${base}/projects`);
    const body = await res.json();
    const items = body.items ?? body;
    return items[0].id;
  }, API_BASE);
}

export async function apiGet<T = unknown>(
  page: Page,
  path: string
): Promise<T> {
  return page.evaluate(
    async ({ base, p }: { base: string; p: string }) => {
      const res = await fetch(`${base}${p}`);
      if (!res.ok) throw new Error(`GET ${p} returned ${res.status}`);
      return res.json();
    },
    { base: API_BASE, p: path }
  );
}

export async function apiPost<T = unknown>(
  page: Page,
  path: string,
  body: unknown
): Promise<T> {
  return page.evaluate(
    async ({ base, p, b }: { base: string; p: string; b: unknown }) => {
      const csrf = document.cookie
        .split("; ")
        .find((c) => c.startsWith("tally_csrf="))
        ?.split("=")[1];
      const res = await fetch(`${base}${p}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrf ? { "X-CSRF-Token": csrf } : {}),
        },
        body: JSON.stringify(b),
      });
      if (!res.ok) throw new Error(`POST ${p} returned ${res.status}`);
      return res.json();
    },
    { base: API_BASE, p: path, b: body }
  );
}

export async function apiPatch<T = unknown>(
  page: Page,
  path: string,
  body: unknown
): Promise<T> {
  return page.evaluate(
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
      if (!res.ok) throw new Error(`PATCH ${p} returned ${res.status}`);
      return res.json();
    },
    { base: API_BASE, p: path, b: body }
  );
}

export async function apiDelete(page: Page, path: string): Promise<void> {
  await page.evaluate(
    async ({ base, p }: { base: string; p: string }) => {
      const csrf = document.cookie
        .split("; ")
        .find((c) => c.startsWith("tally_csrf="))
        ?.split("=")[1];
      const res = await fetch(`${base}${p}`, {
        method: "DELETE",
        headers: csrf ? { "X-CSRF-Token": csrf } : {},
      });
      if (!res.ok) throw new Error(`DELETE ${p} returned ${res.status}`);
    },
    { base: API_BASE, p: path }
  );
}
