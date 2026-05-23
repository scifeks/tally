import { type Locator, type Page, expect } from "@playwright/test";

export class TopBar {
  private readonly nav: Locator;
  private readonly projectButton: Locator;
  private readonly scansIndicator: Locator;

  constructor(private page: Page) {
    this.nav = page.locator("nav");
    this.projectButton = page.getByText("project:");
    this.scansIndicator = page.getByLabel("Open running scans");
  }

  async navigateTo(
    tab:
      | "DASHBOARD"
      | "FINDINGS"
      | "URL LISTS"
      | "SCANS"
      | "TRIAGE"
      | "REPORTS"
      | "CHAT"
      | "CONFIG"
  ): Promise<void> {
    await this.nav.getByText(tab, { exact: true }).click();
  }

  async getActiveTab(): Promise<string> {
    const active = this.nav.locator("a.text-accent, a[aria-current='page']");
    return (await active.textContent()) ?? "";
  }

  async selectProject(projectName: string): Promise<void> {
    await this.projectButton.click();
    await this.page
      .getByRole("menu")
      .getByText(projectName, { exact: false })
      .click();
  }

  async getSelectedProjectName(): Promise<string> {
    return (await this.projectButton.textContent()) ?? "";
  }

  async isNoProjectSelected(): Promise<boolean> {
    const text = await this.getSelectedProjectName();
    return text.includes("select project");
  }

  async getRunningScansText(): Promise<string> {
    return (await this.scansIndicator.textContent()) ?? "";
  }

  async openRunningScansModal(): Promise<void> {
    await this.scansIndicator.click();
  }

  async expectTabVisible(tab: string): Promise<void> {
    await expect(this.nav.getByText(tab, { exact: true })).toBeVisible();
  }

  async expectTabHidden(tab: string): Promise<void> {
    await expect(this.nav.getByText(tab, { exact: true })).toBeHidden();
  }
}
