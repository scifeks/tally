import { test, expect } from "../fixtures/base";
import { apiGet, getProjectId } from "../helpers/common";
import path from "path";
import { fileURLToPath } from "url";

interface UrlEntry {
  id: number;
  method: string;
  protocol: string;
  host: string;
  port: number;
  path: string;
  repoName: string;
}

interface UrlListResponse {
  items: UrlEntry[];
  total: number;
  offset: number;
  limit: number;
}

test.describe.serial("Journey 5: URL List Discovery", () => {
  test("navigates to URL Lists page", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await expect(page).toHaveURL(/\/urls/);
  });

  test("verifies URLs loaded from scans", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?limit=50`
    );

    expect(response.items.length).toBeGreaterThan(0);
    expect(response.total).toBeGreaterThan(0);
  });

  test("filters by GET method", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("GET");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?method=GET&limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);
    for (const item of response.items) {
      expect(item.method).toBe("GET");
    }
  });

  test("filters by POST method", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("POST");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?method=POST&limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);
    for (const item of response.items) {
      expect(item.method).toBe("POST");
    }
  });

  test("applies multi-method filter", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("GET");
    await page.waitForTimeout(300);
    await urlListsPage.selectFilterOption("POST");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?method=GET&method=POST&limit=100`
    );

    const methods = new Set(response.items.map((u) => u.method));
    expect(methods.has("GET")).toBe(true);
    expect(methods.has("POST")).toBe(true);
  });

  test("clears method filter", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("GET");
    await page.waitForTimeout(300);
    await urlListsPage.clearFilters();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const fullResponse = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?limit=50`
    );
    const filteredResponse = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?method=GET&limit=100`
    );

    expect(fullResponse.total).toBeGreaterThan(filteredResponse.total);
  });

  test("filters by protocol", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("protocol");
    await urlListsPage.selectFilterOption("http");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?protocol=http&limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);
    for (const item of response.items) {
      expect(item.protocol).toBe("http");
    }
  });

  test("combines method and protocol filters", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("method");
    await urlListsPage.selectFilterOption("GET");
    await page.waitForTimeout(300);
    await urlListsPage.openFilterDropdown("protocol");
    await urlListsPage.selectFilterOption("http");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?method=GET&protocol=http&limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);
    for (const item of response.items) {
      expect(item.method).toBe("GET");
      expect(item.protocol).toBe("http");
    }
  });

  test("filters by host", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.openFilterDropdown("host");
    await urlListsPage.selectFilterOption("127.0.0.1");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?host=127.0.0.1&limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);
    for (const item of response.items) {
      expect(item.host).toBe("127.0.0.1");
    }
  });

  test("sorts by method ascending", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.sortByColumn("method");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?sort=method&order=asc&limit=50`
    );

    const methods = response.items.map((u) => u.method);
    const sorted = [...methods].sort();
    expect(methods).toEqual(sorted);
  });

  test("sorts by path ascending", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.sortByColumn("path");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?sort=path&order=asc&limit=50`
    );

    const paths = response.items.map((u) => u.path);
    const sorted = [...paths].sort();
    expect(paths).toEqual(sorted);
  });

  test("sorts by path descending", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.sortByColumn("path");
    await page.waitForTimeout(300);
    await urlListsPage.sortByColumn("path");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?sort=path&order=desc&limit=50`
    );

    const paths = response.items.map((u) => u.path);
    const sorted = [...paths].sort().reverse();
    expect(paths).toEqual(sorted);
  });

  test("searches for known DVECA path", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.searchUrls("api");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?search=api&limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);
    for (const item of response.items) {
      expect(item.path.toLowerCase()).toContain("api");
    }
  });

  test("searches with no results", async ({ urlListsPage, page }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.searchUrls("zzz_nonexistent_zzz");
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?search=zzz_nonexistent_zzz&limit=100`
    );

    expect(response.items.length).toBe(0);
  });

  test("clears search and verifies full list", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.searchUrls("test-query");
    await page.waitForTimeout(300);
    await urlListsPage.clearSearch();
    await page.waitForTimeout(500);

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?limit=50`
    );

    expect(response.items.length).toBeGreaterThan(0);
    expect(response.total).toBeGreaterThan(0);
  });

  test("verifies known DVECA endpoints exist", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?limit=100`
    );

    const paths = new Set(response.items.map((u) => u.path));
    const knownPaths = [
      "/api/products.php",
      "/api/chat.php",
      "/index.php",
    ];

    for (const knownPath of knownPaths) {
      expect(paths.has(knownPath)).toBe(true);
    }
  });

  test("verifies URL components are correct", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?limit=50`
    );

    expect(response.items.length).toBeGreaterThan(0);

    const entry = response.items[0];
    expect(entry.id).toBeDefined();
    expect(entry.method).toBeTruthy();
    expect(
      ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"].includes(
        entry.method
      )
    ).toBe(true);
    expect(["http", "https"].includes(entry.protocol)).toBe(true);
    expect(entry.host).toBeTruthy();
    expect(typeof entry.port).toBe("number");
    expect(entry.port).toBeGreaterThan(0);
    expect(entry.path).toBeTruthy();
  });

  test("uploads endpoint file and verifies URLs appear", async ({
    urlListsPage,
    page,
  }) => {
    const fs = await import("fs");
    const dir = path.dirname(fileURLToPath(import.meta.url));
    const fixturePath = path.resolve(
      dir,
      "../fixtures/dveca-endpoints.jsonl"
    );
    const fileBase64 = fs.readFileSync(fixturePath).toString("base64");

    await page.goto("/");
    await page.evaluate(
      async ({ b64, filename }) => {
        const projRes = await fetch("/api/v1/projects");
        const projBody = await projRes.json();
        const pid = projBody.items
          ? projBody.items[0].id
          : projBody[0].id;

        const repoRes = await fetch(
          `/api/v1/projects/${pid}/repositories`
        );
        const repoBody = await repoRes.json();
        const repos = repoBody.items ?? repoBody;
        const dveca = repos.find(
          (r: { name: string }) => r.name === "DVEca"
        );
        if (!dveca) throw new Error("DVEca repo not found");

        const csrf =
          document.cookie
            .split("; ")
            .find((c) => c.startsWith("tally_csrf="))
            ?.split("=")[1] ?? "";

        const bytes = Uint8Array.from(atob(b64), (c) =>
          c.charCodeAt(0)
        );
        const file = new File([bytes], filename, {
          type: "application/x-jsonl",
        });
        const form = new FormData();
        form.append("endpoint_file", file);

        const res = await fetch(
          `/api/v1/projects/${pid}/repositories/${dveca.id}`,
          {
            method: "PATCH",
            headers: { "x-csrf-token": csrf },
            body: form,
          }
        );
        if (!res.ok)
          throw new Error(`Upload failed: ${res.status}`);
      },
      { b64: fileBase64, filename: "dveca-endpoints.jsonl" }
    );

    await urlListsPage.goto();
    await page.waitForTimeout(2000);
    await urlListsPage.expectUrlsVisible();

    const pid = await getProjectId(page);
    const response = await apiGet<UrlListResponse>(
      page,
      `/projects/${pid}/url-list/entries?limit=100`
    );

    expect(response.items.length).toBeGreaterThan(0);

    const paths = response.items.map((u) => u.path);
    expect(paths).toContain("/api/products.php");
  });
});
