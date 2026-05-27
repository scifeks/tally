import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES, TIMEOUTS } from "../fixtures/constants";

export class ScansPage {
  private readonly startButton: Locator;
  private readonly stopButton: Locator;
  private readonly advancedButton: Locator;

  constructor(private page: Page) {
    this.startButton = page.getByRole("button", {
      name: /Start Scan/i,
    });
    this.stopButton = page.getByRole("button", { name: /Stop/i });
    this.advancedButton = page.locator(
      "button:has(svg.lucide-settings-2), button:has(svg.lucide-settings)"
    );
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
      .getByRole("button", { name: domain.toUpperCase(), exact: true })
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
    const status = this.page.locator("[data-testid='scan-status']");
    await expect(status).toHaveText(/completed|cancelled|failed/i, {
      timeout: timeoutMs ?? TIMEOUTS.scan,
    });
  }

  async expectScanRunning(): Promise<void> {
    const status = this.page.locator("[data-testid='scan-status']");
    await expect(status).toHaveText(/running/i, { timeout: 30_000 });
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

  async selectSingleTool(toolName: string): Promise<void> {
    const toolRows = this.page
      .locator(".max-h-56.overflow-y-auto")
      .first()
      .locator("button");
    for (let i = 0; i < (await toolRows.count()); i++) {
      const text = await toolRows.nth(i).textContent();
      if (text?.includes(toolName)) {
        await toolRows.nth(i).click();
        return;
      }
    }
    throw new Error(`Tool "${toolName}" not found in UI`);
  }

  async selectDomainForScan(domain: string): Promise<void> {
    await this.page
      .locator(".flex.flex-wrap.gap-2")
      .first()
      .getByRole("button", { name: domain.toUpperCase(), exact: true })
      .click();
  }

  async excludeTool(toolName: string): Promise<void> {
    const skipSection = this.page.locator(".max-h-56.overflow-y-auto").nth(1);
    const toolRows = skipSection.locator("button");
    for (let i = 0; i < (await toolRows.count()); i++) {
      const text = await toolRows.nth(i).textContent();
      if (text?.includes(toolName)) {
        await toolRows.nth(i).click();
        return;
      }
    }
    throw new Error(`Tool "${toolName}" not found in skip section`);
  }

  async selectArgProfile(profileName: string): Promise<void> {
    const profileSection = this.page
      .locator(".max-h-24.overflow-y-auto")
      .locator("button");
    for (let i = 0; i < (await profileSection.count()); i++) {
      const text = await profileSection.nth(i).textContent();
      if (text?.includes(profileName)) {
        await profileSection.nth(i).click();
        return;
      }
    }
    throw new Error(`Profile "${profileName}" not found`);
  }

  async selectSingleRepo(repoName: string): Promise<void> {
    const repoRows = this.page
      .locator(".max-h-32.overflow-y-auto")
      .first()
      .locator("button");
    for (let i = 0; i < (await repoRows.count()); i++) {
      const text = await repoRows.nth(i).textContent();
      if (text?.includes(repoName)) {
        await repoRows.nth(i).click();
        return;
      }
    }
    throw new Error(`Repo "${repoName}" not found in UI`);
  }

  async confirmDialogIfPresent(): Promise<boolean> {
    const dialog = this.page.locator("[role='dialog']");
    if (await dialog.isVisible({ timeout: 5000 }).catch(() => false)) {
      const confirmBtn = this.page.getByRole("button", { name: /confirm|yes|ok|delete/i });
      if (await confirmBtn.isVisible().catch(() => false)) {
        await confirmBtn.click();
        return true;
      }
    }
    return false;
  }
}
