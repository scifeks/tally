import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES, TIMEOUTS } from "../fixtures/constants";

export class ScansPage {
  private readonly startButton: Locator;
  private readonly stopButton: Locator;

  constructor(private page: Page) {
    this.startButton = page.getByRole("button", {
      name: /Start Scan/i,
    });
    this.stopButton = page.getByRole("button", { name: /Stop/i });
  }

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.scans);
  }

  async startScan(): Promise<void> {
    await this.startButton.click();
  }

  async cancelScan(): Promise<void> {
    await this.stopButton.click();
  }

  async openAdvancedOptions(): Promise<void> {
    const settingsBtn = this.page.locator(
      "button:has(svg.lucide-settings-2), button:has(svg.lucide-settings)"
    );
    if (await settingsBtn.isVisible()) {
      await settingsBtn.click();
    }
  }

  async toggleRepo(name: string): Promise<void> {
    await this.page.getByLabel(name, { exact: false }).click();
  }

  async selectDomain(domain: string): Promise<void> {
    await this.page
      .getByRole("button", { name: domain, exact: true })
      .click();
  }

  async toggleSkipEnrichment(): Promise<void> {
    await this.page
      .getByText("skip", { exact: false })
      .filter({ hasText: /enrich/i })
      .click();
  }

  async switchToHistoryTab(): Promise<void> {
    await this.page
      .getByText("History", { exact: true })
      .click();
  }

  async switchToSavedTab(): Promise<void> {
    await this.page
      .getByText("Saved Scans", { exact: true })
      .click();
  }

  async waitForScanComplete(timeoutMs?: number): Promise<void> {
    await expect(
      this.page
        .getByText(/completed|scan complete|failed/i)
        .first()
    ).toBeVisible({ timeout: timeoutMs ?? TIMEOUTS.scan });
  }

  async expectScanRunning(): Promise<void> {
    await expect(
      this.page.getByText(/running/i).first()
    ).toBeVisible({ timeout: 30_000 });
  }

  async expectScanStatus(status: string): Promise<void> {
    await expect(
      this.page.getByText(status, { exact: false }).first()
    ).toBeVisible();
  }

  async fillSavedScanName(name: string): Promise<void> {
    await this.page.locator("#saved-scan-name").fill(name);
  }

  async saveScanConfig(): Promise<void> {
    await this.page
      .getByRole("button", { name: /save/i })
      .click();
  }

  async selectSavedScan(name: string): Promise<void> {
    await this.page.getByText(name, { exact: true }).click();
  }

  async runSavedScan(): Promise<void> {
    await this.page
      .getByRole("button", { name: /run/i })
      .click();
  }

  async deleteSavedScan(): Promise<void> {
    await this.page
      .getByRole("button", { name: /delete/i })
      .click();
  }

  async expectSavedScanInList(name: string): Promise<void> {
    await expect(
      this.page.getByText(name, { exact: true })
    ).toBeVisible();
  }

  async expectSavedScanNotInList(name: string): Promise<void> {
    await expect(
      this.page.getByText(name, { exact: true })
    ).not.toBeVisible();
  }
}
