import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES } from "../fixtures/constants";
import type { RepoConfig } from "../helpers/repos";

export class ConfigPage {
  private readonly repoSelect: Locator;
  private readonly newRepoButton: Locator;
  private readonly saveButton: Locator;
  private readonly deleteButton: Locator;
  private readonly nameInput: Locator;
  private readonly localPathInput: Locator;

  constructor(private page: Page) {
    this.repoSelect = page.locator("select").first();
    this.newRepoButton = page.getByRole("button", { name: "New" });
    this.saveButton = page.getByRole("button", { name: /^(Save|Create)$/ });
    this.deleteButton = page.getByRole("button", { name: "Delete" });
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

  async fillBaseUrl(url: string): Promise<void> {
    const input = this.page.locator("#svc-base-url");
    await input.fill(url);
  }

  async fillDockerPath(path: string): Promise<void> {
    const input = this.page.locator("#svc-docker-path");
    await input.fill(path);
  }

  async fillContainerName(name: string): Promise<void> {
    const input = this.page.locator("#svc-container-name");
    await input.fill(name);
  }

  async selectServiceType(type: string): Promise<void> {
    const typeSelect = this.page.locator("#svc-type");
    await typeSelect.selectOption(type);
  }

  async selectLocationMode(mode: "local" | "docker"): Promise<void> {
    const radio = this.page.getByLabel(mode, { exact: false });
    await radio.click();
  }

  async toggleLanguage(language: string): Promise<void> {
    await this.page
      .getByRole("button", { name: language, exact: true })
      .click();
  }

  async toggleCrawlEnabled(): Promise<void> {
    const checkbox = this.page.getByText(
      "Also run live crawlers",
      { exact: false }
    );
    await checkbox.click();
  }

  async clickSave(): Promise<void> {
    await this.saveButton.click();
  }

  async clickDelete(): Promise<void> {
    await this.deleteButton.click();
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
      if (label && !label.includes("Select repository")) {
        repoNames.push(label.trim());
      }
    }
    return repoNames;
  }

  async expectRepoCount(count: number): Promise<void> {
    const repos = await this.getRepoOptions();
    expect(repos.length).toBe(count);
  }

  async expectRepoInList(name: string): Promise<void> {
    const repos = await this.getRepoOptions();
    expect(repos).toContain(name);
  }

  async expectRepoNotInList(name: string): Promise<void> {
    const repos = await this.getRepoOptions();
    expect(repos).not.toContain(name);
  }

  async addRepository(repo: RepoConfig): Promise<void> {
    await this.clickNewRepo();
    await this.fillRepoName(repo.name);
    await this.fillLocalPath(repo.localPath);

    if (repo.baseUrl) {
      await this.fillBaseUrl(repo.baseUrl);
    }
    if (repo.dockerPath) {
      await this.fillDockerPath(repo.dockerPath);
    }
    if (repo.containerName) {
      await this.fillContainerName(repo.containerName);
    }

    for (const lang of repo.languages) {
      await this.toggleLanguage(lang);
    }

    await this.clickSave();
    await this.page.waitForTimeout(500);
  }

  async getFieldValue(inputId: string): Promise<string> {
    return this.page.locator(`#${inputId}`).inputValue();
  }

  async expectSaveButtonDisabled(): Promise<void> {
    await expect(this.saveButton).toBeDisabled();
  }

  async expectSaveButtonEnabled(): Promise<void> {
    await expect(this.saveButton).toBeEnabled();
  }
}
