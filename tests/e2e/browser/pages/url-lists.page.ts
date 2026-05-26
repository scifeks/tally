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
      .getByRole("button", { name: `Filter ${column}` })
      .click();
  }

  async selectFilterOption(option: string): Promise<void> {
    const checkbox = this.page.getByRole("checkbox", {
      name: new RegExp(option, "i"),
    });
    await checkbox.waitFor({ state: "visible", timeout: 10_000 });
    await checkbox.click();
  }

  async clearFilters(): Promise<void> {
    await this.page.getByText("clear filters").click();
  }

  async expectUrlsVisible(): Promise<void> {
    await expect(
      this.page.getByText(/\d+ of \d+ loaded/).first()
    ).toBeVisible({ timeout: 10_000 });
  }

  async expectUrlCount(minCount: number): Promise<void> {
    const countText = await this.page
      .getByText(/\d+ of \d+ loaded/)
      .first()
      .textContent();
    const match = countText?.match(/(\d+) of (\d+)/);
    expect(match).not.toBeNull();
    expect(parseInt(match![2], 10)).toBeGreaterThanOrEqual(minCount);
  }

  async getLoadedCount(): Promise<{ loaded: number; total: number }> {
    const countText = await this.page
      .getByText(/\d+ of \d+ loaded/)
      .first()
      .textContent();
    const match = countText?.match(/(\d+) of (\d+)/);
    expect(match).not.toBeNull();
    return {
      loaded: parseInt(match![1], 10),
      total: parseInt(match![2], 10),
    };
  }

  async sortByColumn(columnName: string): Promise<void> {
    await this.page
      .getByRole("button", { name: `Filter ${columnName}` })
      .click();
  }

  async getVisiblePaths(): Promise<string[]> {
    const pathCells = this.page.locator(
      "div[style*='translateY'] div:nth-child(5)"
    );
    const count = await pathCells.count();
    const paths: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await pathCells.nth(i).textContent();
      if (text) {
        paths.push(text);
      }
    }
    return paths;
  }

  async getVisibleMethods(): Promise<string[]> {
    const methodCells = this.page.locator(
      "div[style*='translateY'] div:nth-child(1)"
    );
    const count = await methodCells.count();
    const methods: string[] = [];
    for (let i = 0; i < count; i++) {
      const text = await methodCells.nth(i).textContent();
      if (text) {
        methods.push(text.trim());
      }
    }
    return methods;
  }
}
