import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";

test.describe.serial("Journey 8: Chat", () => {
  test("navigates to chat page", async ({ chatPage, page }) => {
    await chatPage.goto();
    await expect(page).toHaveURL(/\/chat/);
  });

  test("creates a new chat session", async ({ chatPage, page }) => {
    await chatPage.goto();
    await page.waitForTimeout(1000);
    const before = await page
      .locator("[data-testid^='chat-session-']")
      .count();
    await chatPage.createSession();
    await expect(
      page.locator("[data-testid^='chat-session-']")
    ).toHaveCount(before + 1, { timeout: 5000 });
  });

  test("sends a message and receives response", async ({
    chatPage,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.selectSession(0);
    await chatPage.sendMessage(
      "What vulnerabilities did you find?"
    );
    await chatPage.waitForResponse();
  });

  test("sends a follow-up message", async ({ chatPage }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.selectSession(0);
    await chatPage.sendMessage("Summarize the critical findings");
    await chatPage.waitForResponse();
  });

  test("creates a second session", async ({ chatPage, page }) => {
    await chatPage.goto();
    await page.waitForTimeout(1000);
    const before = await page
      .locator("[data-testid^='chat-session-']")
      .count();
    await chatPage.createSession();
    await expect(
      page.locator("[data-testid^='chat-session-']")
    ).toHaveCount(before + 1, { timeout: 5000 });
  });

  test("switches between sessions", async ({ chatPage, page }) => {
    await chatPage.goto();
    await chatPage.selectSession(0);
    await page.waitForTimeout(500);
    await chatPage.selectSession(1);
    await page.waitForTimeout(500);
    await expect(
      page.getByText("SESSION:", { exact: true })
    ).toBeVisible();
  });

  test("deletes a session", async ({ chatPage, page }) => {
    await chatPage.goto();
    await page.waitForTimeout(1000);
    const before = await page
      .locator("[data-testid^='chat-session-']")
      .count();
    await chatPage.deleteSession();
    await expect(
      page.locator("[data-testid^='chat-session-']")
    ).toHaveCount(before - 1, { timeout: 5000 });
  });

  test(
    "receives response mentioning semgrep when asked about semgrep findings",
    async ({ chatPage }) => {
      test.setTimeout(TIMEOUTS.chatStream);
      await chatPage.goto();
      await chatPage.selectSession(0);
      await chatPage.sendMessage("What did semgrep find in the scan?");
      await chatPage.waitForResponse();

      const responseText =
        await chatPage.getLastAssistantMessageText();
      const lower = responseText.toLowerCase();
      const hasFindingContext =
        lower.includes("semgrep") ||
        lower.includes("sast") ||
        lower.includes("finding") ||
        lower.includes("vulnerabilit");
      expect(hasFindingContext).toBeTruthy();
      expect(
        responseText.split(/\s+/).filter((w) => w.length > 0).length
      ).toBeGreaterThan(10);
    }
  );

  test("receives response with severity information", async ({
    chatPage,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.selectSession(0);
    await chatPage.sendMessage(
      "What are the most critical security findings?"
    );
    await chatPage.waitForResponse();

    const responseText = await chatPage.getLastAssistantMessageText();
    const hasSeverityKeyword =
      responseText.toLowerCase().includes("critical") ||
      responseText.toLowerCase().includes("high") ||
      responseText.toLowerCase().includes("severity") ||
      responseText.toLowerCase().includes("vulnerab");
    expect(hasSeverityKeyword).toBeTruthy();
  });

  test("receives response mentioning tool names", async ({
    chatPage,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.selectSession(0);
    await chatPage.sendMessage(
      "Which security tools discovered vulnerabilities?"
    );
    await chatPage.waitForResponse();

    const responseText = await chatPage.getLastAssistantMessageText();
    const toolNames = [
      "semgrep",
      "gitleaks",
      "npm-audit",
      "composer-audit",
      "pip-audit",
      "noir",
    ];
    const mentionedTools = toolNames.filter((tool) =>
      responseText.toLowerCase().includes(tool)
    );
    expect(mentionedTools.length).toBeGreaterThanOrEqual(2);
  });

  test("receives substantial response to summary query", async ({
    chatPage,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.selectSession(0);
    await chatPage.sendMessage(
      "Summarize the scan results"
    );
    await chatPage.waitForResponse();

    const wordCount =
      await chatPage.getAssistantMessageWordCount();
    expect(wordCount).toBeGreaterThan(50);
  });

  test("verifies messages persist after page reload", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.selectSession(0);
    const uniqueText = `E2E persistence check ${Date.now()}`;
    await chatPage.sendMessage(uniqueText);
    await chatPage.waitForResponse();

    await page.reload();
    await page.waitForLoadState("networkidle");
    await chatPage.selectSession(0);

    await expect(
      page.getByText(uniqueText, { exact: false })
    ).toBeVisible({ timeout: 5000 });
  });

  test("verifies messages in separate sessions are independent", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();

    const sessionAIndex = 0;
    await chatPage.selectSession(sessionAIndex);
    const messageA = `Session A message ${Date.now()}`;
    await chatPage.sendMessage(messageA);
    await chatPage.waitForResponse();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    const sessionBIndex = 1;
    await chatPage.selectSession(sessionBIndex);
    const messageB = `Session B message ${Date.now()}`;
    await chatPage.sendMessage(messageB);
    await chatPage.waitForResponse();

    await chatPage.selectSession(sessionAIndex);
    await page.waitForTimeout(500);
    await expect(
      page.getByText(messageA, { exact: false })
    ).toBeVisible();
    await expect(
      page.getByText(messageB, { exact: false })
    ).not.toBeVisible();
  });

  test("verifies session deletion does not affect other sessions", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();

    const initialCount = await page
      .locator("[data-testid^='chat-session-']")
      .count();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.createSession();
    await page.waitForTimeout(500);

    await chatPage.selectSession(initialCount);
    const messageA = `Session A persist ${Date.now()}`;
    await chatPage.sendMessage(messageA);
    await chatPage.waitForResponse();

    await chatPage.selectSession(initialCount + 2);
    const messageC = `Session C persist ${Date.now()}`;
    await chatPage.sendMessage(messageC);
    await chatPage.waitForResponse();

    await chatPage.selectSession(initialCount + 1);
    await chatPage.deleteSession();
    await page.waitForTimeout(500);

    await chatPage.selectSession(initialCount);
    await expect(
      page.getByText(messageA, { exact: false })
    ).toBeVisible();

    await chatPage.selectSession(initialCount + 1);
    await expect(
      page.getByText(messageC, { exact: false })
    ).toBeVisible();
  });

  test("new session starts with empty message history", async ({
    chatPage,
    page,
  }) => {
    await chatPage.goto();
    await chatPage.createSession();
    await page.waitForTimeout(500);

    const assistantCount = await page
      .locator("div:has-text('TALLY')")
      .count();
    expect(assistantCount).toBe(0);
  });

  test("chat history survives session switching", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();

    const initialCount = await page
      .locator("[data-testid^='chat-session-']")
      .count();
    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.createSession();
    await page.waitForTimeout(500);

    await chatPage.selectSession(initialCount);
    const message1 = `History survival test 1 ${Date.now()}`;
    await chatPage.sendMessage(message1);
    await chatPage.waitForResponse();

    await chatPage.selectSession(initialCount + 1);
    const message2 = `History survival test 2 ${Date.now()}`;
    await chatPage.sendMessage(message2);
    await chatPage.waitForResponse();

    await chatPage.selectSession(initialCount);
    await page.waitForTimeout(500);
    await expect(
      page.getByText(message1, { exact: false })
    ).toBeVisible();
  });
});
