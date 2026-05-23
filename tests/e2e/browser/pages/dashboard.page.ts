import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";

export class DashboardPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.dashboard);
  }

  async expectProjectName(name: string): Promise<void> {
    await expect(this.page.getByText(name)).toBeVisible();
  }

  async expectStatValue(label: string, value: string | number): Promise<void> {
    const stat = this.page.getByText(String(value));
    await expect(stat).toBeVisible();
  }

  async expectRecentScanRow(status: string): Promise<void> {
    await expect(
      this.page.getByText(status, { exact: false })
    ).toBeVisible();
  }

  async clickQuickAction(label: string): Promise<void> {
    await this.page.getByText(label, { exact: false }).click();
  }

  async expectEmptyState(): Promise<void> {
    await expect(
      this.page.getByText("Getting started", { exact: false })
    ).toBeVisible();
  }
}
