import { type Locator, type Page, expect } from "@playwright/test";
import { ROUTES, TIMEOUTS } from "../fixtures/constants";

export class ChatPage {
  private readonly newSessionButton: Locator;
  private readonly messageInput: Locator;
  private readonly sendButton: Locator;
  private readonly cancelButton: Locator;

  constructor(private page: Page) {
    this.newSessionButton = page.getByRole("button", { name: /New/i });
    this.messageInput = page.locator(
      "textarea, input[type='text']"
    ).last();
    this.sendButton = page.getByRole("button", { name: /SEND/i });
    this.cancelButton = page.getByRole("button", { name: /CANCEL/i });
  }

  async goto(): Promise<void> {
    await this.page.goto(ROUTES.chat);
  }

  async createSession(): Promise<void> {
    await this.newSessionButton.click();
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
      this.page.locator("[data-role='assistant']").last()
    ).toBeVisible({ timeout: timeoutMs ?? TIMEOUTS.chatStream });
  }

  async selectSession(index: number): Promise<void> {
    const sessions = this.page.locator(
      "[data-testid^='chat-session-']"
    );
    await sessions.nth(index).click();
  }

  async deleteSession(sessionId: number): Promise<void> {
    const session = this.page.locator(
      `[data-testid='chat-session-${sessionId}']`
    );
    await session.getByRole("button").click();
  }

  async expectSessionCount(count: number): Promise<void> {
    const sessions = this.page.locator(
      "[data-testid^='chat-session-']"
    );
    await expect(sessions).toHaveCount(count);
  }

  async expectSealedBadge(): Promise<void> {
    await expect(
      this.page.locator("[data-testid='sealed-badge']")
    ).toBeVisible();
  }
}
