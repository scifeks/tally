import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES, TIMEOUTS } from "../fixtures/constants";

export class ScansPage {
  private readonly startButton: Locator;
  private readonly stopButton: Locator;
  private readonly resetButton: Locator;
  private readonly settingsButton: Locator;

  constructor(private page: Page) {
    this.startButton = page.getByRole("button", { name: /START SCAN/i });
    this.stopButton = page.getByRole("button", { name: /STOP/i });
    this.resetButton = page.getByRole("button", { name: /RESET/i });
    this.settingsButton = page.getByRole("button", { name: /SETTINGS/i });
  }

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.scans);
  }

  async startScan(): Promise<void> {
    await this.startButton.click();
  }

  async stopScan(): Promise<void> {
    await this.stopButton.click();
  }

  async resetScan(): Promise<void> {
    await this.resetButton.click();
  }

  async openAdvancedOptions(): Promise<void> {
    await this.settingsButton.click();
  }

  async selectRepo(name: string): Promise<void> {
    await this.page.getByLabel(name, { exact: false }).check();
  }

  async selectTool(name: string): Promise<void> {
    await this.page.getByLabel(name, { exact: false }).check();
  }

  async selectDomain(domain: string): Promise<void> {
    await this.page.getByText(domain, { exact: true }).click();
  }

  async toggleSkipEnrichment(): Promise<void> {
    await this.page
      .getByText("Skip LLM enrichment", { exact: false })
      .click();
  }

  async switchToHistoryTab(): Promise<void> {
    await this.page.getByText("History", { exact: true }).click();
  }

  async switchToSavedTab(): Promise<void> {
    await this.page.getByText("Saved", { exact: true }).click();
  }

  async switchToLiveLogTab(): Promise<void> {
    await this.page.getByText("Live Log", { exact: true }).click();
  }

  async waitForScanComplete(): Promise<void> {
    await expect(
      this.page.getByText("done", { exact: false })
    ).toBeVisible({ timeout: TIMEOUTS.scan });
  }

  async expectScanStatus(status: string): Promise<void> {
    await expect(
      this.page.getByText(status, { exact: false })
    ).toBeVisible();
  }
}
