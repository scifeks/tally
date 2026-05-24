import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES, TIMEOUTS } from "../fixtures/constants";

export class ChatPage {
  private readonly messageInput: Locator;
  private readonly sendButton: Locator;
  private readonly cancelButton: Locator;

  constructor(private page: Page) {
    this.messageInput = page.getByPlaceholder(
      "Ask about your security findings..."
    );
    this.sendButton = page.locator(
      "button[aria-label='send message']"
    );
    this.cancelButton = page.locator(
      "button[aria-label='cancel stream']"
    );
  }

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.chat);
  }

  async createSession(): Promise<void> {
    await this.page
      .getByRole("button", { name: /new/i })
      .click();
  }

  async sendMessage(text: string): Promise<void> {
    await this.messageInput.fill(text);
    await this.sendButton.click();
  }

  async cancelStream(): Promise<void> {
    await this.cancelButton.click();
  }

  async waitForResponse(timeoutMs?: number): Promise<void> {
    await expect(
      this.page.getByText("TALLY").last()
    ).toBeVisible({ timeout: timeoutMs ?? TIMEOUTS.chatStream });
  }

  async selectSession(index: number): Promise<void> {
    await this.page
      .locator("[data-testid^='chat-session-']")
      .nth(index)
      .click();
  }

  async deleteSession(): Promise<void> {
    await this.page
      .locator("button[aria-label='delete session']")
      .first()
      .click();
  }

  async expectSessionCount(count: number): Promise<void> {
    await expect(
      this.page.locator("[data-testid^='chat-session-']")
    ).toHaveCount(count);
  }

  async expectSealedBadge(): Promise<void> {
    await expect(
      this.page.locator("[data-testid='sealed-badge']")
    ).toBeVisible();
  }

  async expectMessageVisible(text: string): Promise<void> {
    await expect(
      this.page.getByText(text, { exact: false })
    ).toBeVisible();
  }
}
