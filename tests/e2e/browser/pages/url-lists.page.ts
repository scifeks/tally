import { type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";

export class UrlListsPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.urls);
  }

  async searchUrls(query: string): Promise<void> {
    await this.page
      .locator("input[aria-label='Search URLs']")
      .fill(query);
  }

  async clearSearch(): Promise<void> {
    await this.page
      .locator("button[aria-label='Clear search']")
      .click();
  }

  async openFilterDropdown(column: string): Promise<void> {
    await this.page
      .getByText(column, { exact: true })
      .locator("..")
      .locator("button")
      .last()
      .click();
  }

  async selectFilterOption(option: string): Promise<void> {
    await this.page.getByText(option, { exact: true }).click();
  }

  async clearFilters(): Promise<void> {
    await this.page.getByText("clear filters").click();
  }

  async expectUrlsVisible(): Promise<void> {
    await expect(
      this.page.getByText(/\d+ of \d+ loaded/)
    ).toBeVisible({ timeout: 10_000 });
  }

  async expectUrlCount(minCount: number): Promise<void> {
    const countText = await this.page
      .getByText(/\d+ of \d+ loaded/)
      .textContent();
    const match = countText?.match(/(\d+) of (\d+)/);
    expect(match).not.toBeNull();
    expect(parseInt(match![2], 10)).toBeGreaterThanOrEqual(minCount);
  }
}
