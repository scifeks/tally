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
      .getByRole("button", { name: "New Chat" }).first()
      .click();
  }

  async sendMessage(text: string): Promise<void> {
    await expect(this.messageInput).toBeEnabled({
      timeout: TIMEOUTS.chatStream,
    });
    await this.messageInput.fill(text);
    await expect(this.sendButton).toBeEnabled({ timeout: 5000 });
    await this.sendButton.click();
  }

  async cancelStream(): Promise<void> {
    await this.cancelButton.click();
  }

  async waitForResponse(timeoutMs?: number): Promise<void> {
    const timeout = timeoutMs ?? TIMEOUTS.chatStream;
    const streaming = this.page.getByText("STREAMING");
    await expect(streaming).toBeVisible({ timeout: 10_000 });
    await expect(streaming).not.toBeVisible({ timeout });
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

  async getLastAssistantMessageText(): Promise<string> {
    const assistantMessages = this.page.locator(
      ".whitespace-pre-wrap.bg-muted\\/50"
    );
    return (await assistantMessages.last().textContent()) ?? "";
  }

  async getMessageCount(): Promise<number> {
    return this.page
      .locator("div:has(> div:has-text('YOU', 'TALLY'))")
      .count();
  }

  async getAssistantMessageWordCount(): Promise<number> {
    const text = await this.getLastAssistantMessageText();
    return text.split(/\s+/).filter((w) => w.length > 0).length;
  }

  async waitForResponseContaining(
    keyword: string,
    timeoutMs?: number
  ): Promise<void> {
    const timeout = timeoutMs ?? TIMEOUTS.chatStream;
    await this.page.waitForFunction(
      (searchKeyword: unknown) => {
        const kw = searchKeyword as string;
        const tallyLabels = Array.from(
          document.querySelectorAll("div")
        ).filter((el) => el.textContent?.includes("TALLY"));
        if (tallyLabels.length === 0) return false;
        const lastTallyLabel = tallyLabels[tallyLabels.length - 1];
        const messageParent = lastTallyLabel.closest(".flex-col");
        if (!messageParent) return false;
        const contentDiv = messageParent.querySelector(".whitespace-pre-wrap");
        return (
          contentDiv?.textContent
            ?.toLowerCase()
            .includes(kw.toLowerCase()) ?? false
        );
      },
      keyword,
      { timeout }
    );
  }
}
