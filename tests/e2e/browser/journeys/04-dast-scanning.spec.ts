import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";
import { getProjectId, apiGet } from "../helpers/common";

test.describe.serial("Journey 4: DAST Scanning", () => {
  test("starts web scan and waits for completion", async ({
    scansPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.scan);
    await scansPage.goto();

    const pid = await getProjectId(page);

    await page.evaluate(
      async ({ pid, csrf }: { pid: number; csrf: string }) => {
        const res = await fetch(`/api/v1/projects/${pid}/scans`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-csrf-token": csrf,
          },
          body: JSON.stringify({
            skipEnrichment: true,
            toolIds: ["noir"],
          }),
        });
        if (!res.ok)
          throw new Error(`Scan start failed: ${res.status}`);
      },
      {
        pid,
        csrf:
          document.cookie
            ?.split("; ")
            .find((c: string) => c.startsWith("tally_csrf="))
            ?.split("=")[1] ?? "",
      }
    );

    await scansPage.expectScanRunning();
    await scansPage.waitForScanComplete();

    const findings = await apiGet<{
      items: { tool: string }[];
      total: number;
    }>(page, `/projects/${pid}/findings?tool=noir&limit=1`);
    expect(findings.total).toBeGreaterThan(0);
    expect(findings.items[0].tool).toBe("noir");
  });

  test("verifies web scan in history", async ({
    scansPage,
    page,
  }) => {
    await scansPage.goto();
    await scansPage.switchToHistoryTab();
    await scansPage.expectScanStatus("done");

    const pid = await getProjectId(page);
    const scans = await apiGet<{
      items: { status: string; findings_count: number }[];
    }>(page, `/projects/${pid}/scans?limit=1`);
    expect(scans.items[0].status).toBe("completed");
    expect(scans.items[0].findings_count).toBeGreaterThan(0);
  });

  test("verifies URL list has entries from crawl", async ({
    urlListsPage,
    page,
  }) => {
    await urlListsPage.goto();
    await urlListsPage.expectUrlsVisible();
    await urlListsPage.expectUrlCount(1);

    const pid = await getProjectId(page);
    const urls = await apiGet<{
      items: { source: string }[];
      total: number;
    }>(page, `/projects/${pid}/url-list/entries?limit=5`);
    expect(urls.total).toBeGreaterThan(0);
  });
});
