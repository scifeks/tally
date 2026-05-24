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
}
