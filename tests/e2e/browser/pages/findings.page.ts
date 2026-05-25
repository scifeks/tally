import { type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";

export class FindingsPage {
  constructor(private page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.findings);
  }

  async selectSegment(segment: string): Promise<void> {
    await this.page
      .getByRole("button", { name: segment.toUpperCase() })
      .click();
  }

  async toggleSeverityFilter(severity: string): Promise<void> {
    await this.page
      .getByRole("button", {
        name: new RegExp(`^${severity}`, "i"),
      })
      .click();
  }

  async searchFindings(query: string): Promise<void> {
    await this.page.keyboard.press("/");
    await this.page.waitForTimeout(200);
    await this.page.keyboard.type(query);
  }

  async clearSearch(): Promise<void> {
    await this.page.keyboard.press("/");
    await this.page.waitForTimeout(200);
    await this.page.keyboard.press("Control+a");
    await this.page.keyboard.press("Backspace");
    await this.page.keyboard.press("Escape");
  }

  async clearFilters(): Promise<void> {
    await this.page.getByText("clear filters", { exact: false }).click();
  }

  async clickFindingRow(index: number): Promise<void> {
    const rows = this.page.locator("[role='button'][data-index]");
    await rows.nth(index).click();
  }

  async selectFindingCheckbox(index: number): Promise<void> {
    await this.page
      .locator("input[type='checkbox'][aria-label^='Select ']")
      .nth(index)
      .check();
  }

  async editTitle(newTitle: string): Promise<void> {
    await this.page
      .locator("[aria-label='Edit finding title']")
      .first()
      .click();
    const titleInput = this.page.locator(
      "input[aria-label='Edit finding title']"
    );
    await titleInput.fill(newTitle);
    await titleInput.press("Enter");
  }

  async editNotes(notes: string): Promise<void> {
    await this.page
      .locator("[aria-label='Edit notes']")
      .first()
      .click();
    const notesInput = this.page.locator(
      "textarea[aria-label='Edit notes']"
    );
    await notesInput.fill(notes);
    await notesInput.press("Enter");
  }

  async markFixed(): Promise<void> {
    await this.page.getByText("mark fixed", { exact: true }).click();
  }

  async markFalsePositive(): Promise<void> {
    await this.page.getByText("false-pos", { exact: true }).click();
  }

  async markWontFix(): Promise<void> {
    await this.page.getByText("wontfix", { exact: true }).click();
  }

  async deleteFinding(): Promise<void> {
    await this.page
      .getByText("delete finding", { exact: true })
      .click();
  }

  async confirmDelete(): Promise<void> {
    await this.page
      .getByText("confirm delete", { exact: true })
      .click();
  }

  async openCreateFindingModal(): Promise<void> {
    await this.page
      .getByRole("button", { name: /add issue/i })
      .click();
  }

  async fillManualFindingTitle(title: string): Promise<void> {
    await this.page.getByPlaceholder("finding title").fill(title);
  }

  async selectManualFindingSeverity(severity: string): Promise<void> {
    await this.page
      .getByLabel("SEVERITY", { exact: false })
      .selectOption(severity);
  }

  async fillManualFindingUrl(url: string): Promise<void> {
    await this.page.getByPlaceholder("url").fill(url);
  }

  async submitManualFinding(): Promise<void> {
    await this.page
      .getByRole("button", { name: /create/i })
      .last()
      .click();
  }

  async expectFindingsVisible(): Promise<void> {
    await expect(
      this.page.locator("[role='button'][data-index]").first()
    ).toBeVisible({ timeout: 10_000 });
  }

  async expectDetailPanelVisible(): Promise<void> {
    await expect(
      this.page.getByText("detail ::", { exact: false })
    ).toBeVisible();
  }

  async getVisibleFindingCount(): Promise<number> {
    const rows = this.page.locator("[role='button'][data-index]");
    return rows.count();
  }

  async editStatus(status: string): Promise<void> {
    const select = this.page
      .locator("[aria-label='Edit status']")
      .first();
    await select.click();
    await this.page.waitForTimeout(200);
    await this.page.getByRole("option", { name: new RegExp(status, "i") }).first().click();
  }

  async editShouldReport(shouldReport: boolean): Promise<void> {
    const checkbox = this.page.locator(
      "input[aria-label='should report finding']"
    );
    if (shouldReport) {
      await checkbox.check();
    } else {
      await checkbox.uncheck();
    }
  }

  async editBusinessImpact(impact: string): Promise<void> {
    const notesField = this.page.locator(
      "textarea[aria-label='Edit notes']"
    );
    await notesField.click();
    await notesField.fill(impact);
    await notesField.press("Enter");
  }

  async selectManualFindingStatus(status: string): Promise<void> {
    await this.page
      .getByLabel("STATUS", { exact: false })
      .selectOption(status);
  }

  async selectManualFindingTool(tool: string): Promise<void> {
    await this.page
      .getByLabel("TOOL", { exact: false })
      .selectOption(tool);
  }
}
