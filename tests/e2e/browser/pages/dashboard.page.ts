import { type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";

export class DashboardPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.dashboard);
  }

  async expectProjectName(name: string): Promise<void> {
    await expect(
      this.page.getByText(name).first()
    ).toBeVisible();
  }

  async expectStatTile(label: string, minValue: number): Promise<void> {
    const tile = this.page
      .getByText(label, { exact: false })
      .first()
      .locator("..");
    await expect(tile).toBeVisible();
    const tileText = await tile.textContent();
    const match = tileText?.match(/(\d+)/);
    expect(match).not.toBeNull();
    expect(parseInt(match![1], 10)).toBeGreaterThanOrEqual(minValue);
  }

  async expectRecentScanRow(status: string): Promise<void> {
    await expect(
      this.page.getByText(status, { exact: false })
    ).toBeVisible();
  }

  async clickQuickAction(label: string): Promise<void> {
    await this.page
      .getByText(label, { exact: false })
      .click();
  }

  async expectNotEmpty(): Promise<void> {
    await expect(
      this.page.getByText("new scan", { exact: false })
    ).toBeVisible();
  }
}
