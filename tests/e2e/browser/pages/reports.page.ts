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

  async waitForDraftComplete(
    section: string,
    timeoutMs: number = TIMEOUTS.reportGeneration
  ): Promise<void> {
    const draftCard = this.page.locator(
      `[data-testid='report-draft-${section}-generate']`
    );
    await expect(draftCard).toBeEnabled({ timeout: timeoutMs });
  }

  async waitForReportComplete(
    timeoutMs: number = TIMEOUTS.reportGeneration
  ): Promise<void> {
    const resetButton = this.page.locator(
      "[data-testid='report-reset-button']"
    );
    await expect(resetButton).toBeVisible({ timeout: timeoutMs });
  }

  async getDraftStatus(section: string): Promise<string | null> {
    const statusText = this.page.locator(
      `[data-testid='report-draft-${section}-status']`
    );
    return statusText.textContent();
  }

  async clickRegenerate(section: string): Promise<void> {
    await this.page
      .locator(`[data-testid='report-draft-${section}-regenerate']`)
      .click();
  }

  async getReportHistoryCount(): Promise<number> {
    const rows = this.page.locator(
      "[data-testid^='report-history-row-']"
    );
    return rows.count();
  }

  async editReportName(newName: string): Promise<void> {
    const nameInput = this.page.locator(
      "[data-testid='report-detail-name']"
    );
    await nameInput.click();
    await nameInput.fill(newName);
    await nameInput.blur();
  }

  async editReportNotes(newNotes: string): Promise<void> {
    const notesInput = this.page.locator(
      "[data-testid='report-detail-notes']"
    );
    await notesInput.click();
    await notesInput.fill(newNotes);
    await notesInput.blur();
  }

  async deleteReport(): Promise<void> {
    await this.page
      .locator("[data-testid='report-detail-delete']")
      .click();
  }

  async confirmDelete(): Promise<void> {
    this.page.once("dialog", dialog => {
      void dialog.accept();
    });
  }

  async selectReportFromHistory(reportId: number): Promise<void> {
    await this.page
      .locator(`[data-testid='report-history-row-${reportId}']`)
      .click();
  }
}
