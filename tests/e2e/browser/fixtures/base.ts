import { test as base } from "@playwright/test";
import { DashboardPage } from "../pages/dashboard.page";
import { ConfigPage } from "../pages/config.page";
import { ScansPage } from "../pages/scans.page";
import { FindingsPage } from "../pages/findings.page";
import { UrlListsPage } from "../pages/url-lists.page";
import { ReportsPage } from "../pages/reports.page";
import { ChatPage } from "../pages/chat.page";
import { TopBar } from "../pages/top-bar.page";

type TestFixtures = {
  dashboardPage: DashboardPage;
  configPage: ConfigPage;
  scansPage: ScansPage;
  findingsPage: FindingsPage;
  urlListsPage: UrlListsPage;
  reportsPage: ReportsPage;
  chatPage: ChatPage;
  topBar: TopBar;
};

export const test = base.extend<TestFixtures>({
  dashboardPage: async ({ page }, use) => {
    await use(new DashboardPage(page));
  },
  configPage: async ({ page }, use) => {
    await use(new ConfigPage(page));
  },
  scansPage: async ({ page }, use) => {
    await use(new ScansPage(page));
  },
  findingsPage: async ({ page }, use) => {
    await use(new FindingsPage(page));
  },
  urlListsPage: async ({ page }, use) => {
    await use(new UrlListsPage(page));
  },
  reportsPage: async ({ page }, use) => {
    await use(new ReportsPage(page));
  },
  chatPage: async ({ page }, use) => {
    await use(new ChatPage(page));
  },
  topBar: async ({ page }, use) => {
    await use(new TopBar(page));
  },
});

export { expect } from "@playwright/test";
