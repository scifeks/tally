import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";
import type { RepoConfig } from "../helpers/repos";

export class ConfigPage {
  private readonly repoSelect: Locator;
  private readonly newRepoButton: Locator;
  private readonly nameInput: Locator;
  private readonly localPathInput: Locator;

  constructor(private page: Page) {
    this.repoSelect = page.locator("select").first();
    this.newRepoButton = page.getByRole("button", { name: "New" });
    this.nameInput = page.locator("#repo-name");
    this.localPathInput = page.locator("#repo-local-path");
  }

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.config);
  }

  async clickNewRepo(): Promise<void> {
    await this.newRepoButton.click();
  }

  async fillRepoName(name: string): Promise<void> {
    await this.nameInput.fill(name);
  }

  async fillLocalPath(path: string): Promise<void> {
    await this.localPathInput.fill(path);
  }

  async selectServiceType(type: string): Promise<void> {
    await this.page
      .getByRole("button", { name: type, exact: true })
      .first()
      .click();
  }

  async selectLocationMode(mode: "local" | "docker"): Promise<void> {
    await this.page
      .getByRole("button", { name: mode, exact: true })
      .first()
      .click();
  }

  async fillContainerName(name: string): Promise<void> {
    await this.page.locator("#svc-container-name").fill(name);
  }

  async fillMountPoint(path: string): Promise<void> {
    await this.page.locator("#svc-mount-point").fill(path);
  }

  async addLanguage(language: string): Promise<void> {
    const langLabel = this.page
      .getByText("Languages", { exact: false })
      .first();
    const input = langLabel.locator("..").getByRole("textbox");
    await input.scrollIntoViewIfNeeded();
    await input.fill(language);
    await input.press("Enter");
  }

  async addBaseUrl(url: string): Promise<void> {
    const urlLabel = this.page
      .getByText("Base URLs", { exact: false })
      .first();
    const input = urlLabel.locator("..").getByRole("textbox");
    await input.scrollIntoViewIfNeeded();
    await input.fill(url);
    await input.press("Enter");
  }

  async clickSave(): Promise<void> {
    await this.page
      .getByRole("button", { name: /^(Save|Create)$/i })
      .first()
      .click();
  }

  async clickDelete(): Promise<void> {
    await this.page
      .getByRole("button", { name: /Delete/i })
      .first()
      .click();
  }

  async selectRepoByName(name: string): Promise<void> {
    await this.repoSelect.selectOption({ label: name });
  }

  async getRepoOptions(): Promise<string[]> {
    const options = this.repoSelect.locator("option");
    const repoNames: string[] = [];
    const count = await options.count();
    for (let i = 0; i < count; i++) {
      const label = await options.nth(i).textContent();
      if (label && !label.includes("Select")) {
        repoNames.push(label.trim());
      }
    }
    return repoNames;
  }

  async expectRepoCount(count: number): Promise<void> {
    await expect
      .poll(() => this.getRepoOptions().then((r) => r.length), {
        timeout: 10_000,
      })
      .toBe(count);
  }

  async expectRepoInList(name: string): Promise<void> {
    await expect
      .poll(() => this.getRepoOptions(), { timeout: 10_000 })
      .toContain(name);
  }

  async expectRepoNotInList(name: string): Promise<void> {
    await expect
      .poll(() => this.getRepoOptions(), { timeout: 10_000 })
      .not.toContain(name);
  }

  async addRepository(repo: RepoConfig): Promise<void> {
    await this.clickNewRepo();
    await this.fillRepoName(repo.name);
    await this.fillLocalPath(repo.localPath);

    for (const svcType of repo.serviceTypes) {
      await this.selectServiceType(svcType);
    }

    if (repo.locationMode === "docker" && repo.containerName) {
      await this.selectLocationMode("docker");
      await this.fillContainerName(repo.containerName);
      if (repo.mountPoint) {
        await this.fillMountPoint(repo.mountPoint);
      }
    }

    for (const lang of repo.languages) {
      await this.addLanguage(lang);
    }

    if (repo.baseUrl) {
      await this.addBaseUrl(repo.baseUrl);
    }

    await this.clickSave();
    await this.page.waitForTimeout(500);
  }

  async getFieldValue(inputId: string): Promise<string> {
    return this.page.locator(`#${inputId}`).inputValue();
  }

  async expectSaveButtonDisabled(): Promise<void> {
    await expect(
      this.page
        .getByRole("button", { name: /^(Save|Create)$/i })
        .first()
    ).toBeDisabled();
  }

  async expectSaveButtonEnabled(): Promise<void> {
    await expect(
      this.page
        .getByRole("button", { name: /^(Save|Create)$/i })
        .first()
    ).toBeEnabled();
  }

  async addToolOverride(toolName: string): Promise<void> {
    const addSelect = this.page.locator("select").last();
    await addSelect.selectOption({ label: toolName });
  }

  async selectToolOverride(toolName: string): Promise<void> {
    const overrides = this.page.locator("select").nth(1);
    await overrides.selectOption({ label: toolName });
  }

  async setOverrideType(type: "repo" | "api"): Promise<void> {
    await this.page
      .getByRole("button", { name: type, exact: true })
      .last()
      .click();
  }

  async setOverrideLocation(location: "local" | "docker"): Promise<void> {
    await this.page
      .getByRole("button", { name: location, exact: true })
      .last()
      .click();
  }

  async setOverrideArgsMode(mode: "stock" | "custom"): Promise<void> {
    await this.page
      .getByRole("button", { name: mode, exact: true })
      .click();
  }

  async fillToolPath(path: string): Promise<void> {
    await this.page.locator("#tool-path").fill(path);
  }

  async saveToolOverride(): Promise<void> {
    await this.page
      .getByRole("button", { name: /^(Save|Create)$/i })
      .last()
      .click();
  }

  async deleteToolOverride(): Promise<void> {
    await this.page
      .getByRole("button", { name: /Remove Override/i })
      .click();
  }

  async addArgumentTemplate(name: string): Promise<void> {
    await this.page
      .getByRole("button", { name: /Add Template/i })
      .click();
    await this.page.locator("input[id^='tmpl-name-']").last().fill(name);
  }

  async fillAuthLoginUrl(url: string): Promise<void> {
    await this.page.locator("#repo-auth-login-url").fill(url);
  }

  async fillAuthUsername(username: string): Promise<void> {
    await this.page.locator("#repo-auth-username").fill(username);
  }

  async fillAuthPassword(password: string): Promise<void> {
    await this.page.locator("#repo-auth-password").fill(password);
  }

  async saveAuth(): Promise<void> {
    await this.page
      .getByRole("button", { name: /Save Auth/i })
      .click();
  }

  async expectAuthSaved(): Promise<void> {
    await expect(
      this.page.getByText("Saved", { exact: false }).first()
    ).toBeVisible({ timeout: 5000 });
  }

  async toggleHeadlessMode(): Promise<void> {
    const headlessCheckbox = this.page
      .getByText("Katana headless mode", { exact: false })
      .locator("..");
    const button = headlessCheckbox.locator("button").first();
    await button.click();
  }

  async setCrawlDepth(depth: number): Promise<void> {
    await this.page.locator("#repo-crawl-depth").fill(String(depth));
  }

  async uploadEndpointFile(filePath: string): Promise<void> {
    await this.page.locator("#repo-endpoint-file").setInputFiles(filePath);
  }

  async uploadGarakConfig(filePath: string): Promise<void> {
    await this.page.locator("#repo-garak-config").setInputFiles(filePath);
  }

  async toggleAdvancedMode(): Promise<void> {
    await this.page
      .getByRole("button", { name: "advanced", exact: true })
      .first()
      .click();
  }

  async addService(name: string): Promise<void> {
    const addBtn = this.page
      .getByRole("button", { name: /Add|Add Service/i })
      .filter({ hasText: /add|plus/i });
    await addBtn.first().click();
    await this.page.waitForTimeout(300);
  }

  async removeService(name: string): Promise<void> {
    const servicePanel = this.page
      .locator("div")
      .filter({ hasText: new RegExp(`^${name}$`) });
    const removeBtn = servicePanel.getByRole("button", { name: /remove|delete/i });
    await removeBtn.click();
  }

  async fillServiceBaseUrl(url: string): Promise<void> {
    const urlLabel = this.page
      .getByText("Base URLs", { exact: false })
      .first();
    const input = urlLabel.locator("..").getByRole("textbox");
    await input.scrollIntoViewIfNeeded();
    await input.fill(url);
    await input.press("Enter");
  }

  async openArgumentTemplates(): Promise<void> {
    await this.page
      .getByText("Argument Templates", { exact: false })
      .first()
      .click();
  }

  async addTemplateArg(
    flag: string,
    valueType: string,
    value?: string
  ): Promise<void> {
    await this.page
      .getByRole("button", { name: /Add|plus/i })
      .filter({ hasText: /arg/i })
      .last()
      .click();
    await this.page.waitForTimeout(200);

    const lastArgRow = this.page.locator("input[placeholder*='flag']").last();
    await lastArgRow.fill(flag);

    if (valueType !== "none") {
      const typeSelect = this.page.locator("select").last();
      await typeSelect.selectOption(valueType);
    }

    if (value && valueType !== "file") {
      const valueInput = this.page.locator("input[placeholder*='value']").last();
      await valueInput.fill(value);
    }
  }

  async saveArgumentTemplate(): Promise<void> {
    await this.page
      .getByRole("button", { name: /Save|Done/i })
      .last()
      .click();
  }

  async deleteArgumentTemplate(name: string): Promise<void> {
    const template = this.page
      .locator("div")
      .filter({ hasText: new RegExp(`^${name}`) });
    const deleteBtn = template.getByRole("button", { name: /delete/i });
    await deleteBtn.click();
  }
}
