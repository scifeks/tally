import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES, TIMEOUTS } from "../fixtures/constants";

export class ReportsPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.reports);
  }

  async selectFormat(format: string): Promise<void> {
    await this.page
      .locator("[data-testid='report-format-select']")
      .selectOption(format);
  }

  async selectTestingType(type: string): Promise<void> {
    await this.page
      .locator("[data-testid='report-testing-type-select']")
      .selectOption(type);
  }

  async fillCompanyName(name: string): Promise<void> {
    await this.page
      .locator("[data-testid='report-company-name-input']")
      .fill(name);
  }

  async fillEngagementDate(date: string): Promise<void> {
    await this.page
      .locator("[data-testid='report-engagement-date-input']")
      .fill(date);
  }

  async toggleSkipTriage(): Promise<void> {
    await this.page
      .locator("[data-testid='report-skip-triage-checkbox']")
      .click();
  }

  async clickGenerateReport(): Promise<void> {
    await this.page
      .locator("[data-testid='report-generate-button']")
      .click();
  }

  async clickGenerateMissing(): Promise<void> {
    await this.page
      .locator("[data-testid='report-generate-missing-button']")
      .click();
  }

  async clickStopGeneration(): Promise<void> {
    await this.page
      .locator("[data-testid='report-stop-button']")
      .click();
  }

  async generateDraftSection(section: string): Promise<void> {
    await this.page
      .locator(`[data-testid='report-draft-${section}-generate']`)
      .click();
  }

  async uploadDraft(section: string, filePath: string): Promise<void> {
    const input = this.page.locator(
      `[data-testid='report-draft-${section}-file-input']`
    );
    await input.setInputFiles(filePath);
    await this.page
      .locator(`[data-testid='report-draft-${section}-upload']`)
      .click();
  }

  async deleteDraft(section: string): Promise<void> {
    await this.page
      .locator(`[data-testid='report-draft-${section}-delete']`)
      .click();
  }

  async downloadReport(reportId: number): Promise<void> {
    await this.page
      .locator(`[data-testid='report-history-download-${reportId}']`)
      .click();
  }

  async switchToHistoryTab(): Promise<void> {
    await this.page.getByText("History", { exact: true }).click();
  }

  async expectReportInHistory(filename: string): Promise<void> {
    await expect(
      this.page.getByText(filename, { exact: false })
    ).toBeVisible();
  }
}
