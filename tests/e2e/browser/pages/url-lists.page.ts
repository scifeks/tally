import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";

export class UrlListsPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.urls);
  }

  async searchUrls(query: string): Promise<void> {
    const input = this.page.getByPlaceholder(/search/i);
    await input.fill(query);
  }

  async filterByMethod(method: string): Promise<void> {
    await this.page.getByText(method, { exact: true }).click();
  }

  async filterByHost(host: string): Promise<void> {
    await this.page.getByText(host, { exact: true }).click();
  }

  async filterByRepo(repo: string): Promise<void> {
    await this.page.getByText(repo, { exact: true }).click();
  }

  async clearFilters(): Promise<void> {
    await this.page
      .getByRole("button", { name: /clear/i })
      .click();
  }

  async expectUrlsVisible(): Promise<void> {
    await expect(this.page.locator("table, [role='grid']")).toBeVisible();
  }
}
