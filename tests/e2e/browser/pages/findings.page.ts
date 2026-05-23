import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";

export class FindingsPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.findings);
  }

  async selectSegment(segment: string): Promise<void> {
    await this.page.getByText(segment, { exact: true }).click();
  }

  async toggleSeverity(severity: string): Promise<void> {
    await this.page.getByText(severity, { exact: true }).click();
  }

  async searchFindings(query: string): Promise<void> {
    const input = this.page.getByPlaceholder(/search/i);
    await input.fill(query);
  }

  async clearFilters(): Promise<void> {
    await this.page
      .getByRole("button", { name: /clear/i })
      .click();
  }

  async clickFinding(index: number): Promise<void> {
    const rows = this.page.locator("[data-finding-row]");
    await rows.nth(index).click();
  }

  async selectFinding(index: number): Promise<void> {
    const checkboxes = this.page.locator(
      "input[type='checkbox']"
    );
    await checkboxes.nth(index).check();
  }

  async bulkMarkFalsePositive(): Promise<void> {
    await this.page
      .getByRole("button", { name: /MARK FALSE-POS/i })
      .click();
  }

  async bulkMarkFixed(): Promise<void> {
    await this.page
      .getByRole("button", { name: /MARK FIXED/i })
      .click();
  }

  async openCreateFindingModal(): Promise<void> {
    await this.page
      .getByRole("button", { name: /ADD ISSUE/i })
      .click();
  }

  async expectFindingsVisible(): Promise<void> {
    await expect(this.page.locator("table, [role='grid']")).toBeVisible();
  }
}
