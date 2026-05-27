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
    await chatPage.createSession();
    await page.waitForTimeout(500);
    await expect(
      page.getByText("0 msgs").first()
    ).toBeVisible({ timeout: 5000 });
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
    await chatPage.createSession();
    await page.waitForTimeout(500);
    await expect(
      page.getByText("0 msgs").first()
    ).toBeVisible({ timeout: 5000 });
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
    await chatPage.createSession();
    await page.waitForTimeout(500);

    const firstSession = page
      .locator("[data-testid^='chat-session-']")
      .first();
    const sessionTestId = await firstSession.getAttribute("data-testid");

    await chatPage.selectSession(0);
    await page.waitForTimeout(300);
    await chatPage.deleteSession();
    await page.waitForTimeout(1000);

    const deletedSession = page.locator(
      `[data-testid='${sessionTestId}']`
    );
    await expect(deletedSession).not.toBeVisible({ timeout: 5000 });
  });

  test(
    "receives response mentioning semgrep when asked about semgrep findings",
    async ({ chatPage, page }) => {
      test.setTimeout(TIMEOUTS.chatStream);
      await chatPage.goto();
      await chatPage.createSession();
      await page.waitForTimeout(500);
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
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.createSession();
    await page.waitForTimeout(500);
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
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.sendMessage(
      "Which security tools discovered vulnerabilities?"
    );
    await chatPage.waitForResponse();

    const responseText = await chatPage.getLastAssistantMessageText();
    const toolNames = [
      "semgrep", "gitleaks", "trufflehog", "noir",
      "osv-scanner", "zap", "sqlmap", "xsstrike",
      "katana", "nuclei", "dalfox", "garak",
      "npm-audit", "composer-audit", "pip-audit",
    ];
    const mentionedTools = toolNames.filter((tool) =>
      responseText.toLowerCase().includes(tool)
    );
    expect(mentionedTools.length).toBeGreaterThanOrEqual(1);
  });

  test("receives substantial response to summary query", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();
    await chatPage.createSession();
    await page.waitForTimeout(500);
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
    await page.waitForLoadState("domcontentloaded");
    await page.waitForTimeout(1000);
    await chatPage.selectSession(0);

    await expect(
      page.getByText(uniqueText, { exact: false }).first()
    ).toBeVisible({ timeout: 5000 });
  });

  test("verifies messages in separate sessions are independent", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.selectSession(0);
    const messageA = `Session A message ${Date.now()}`;
    await chatPage.sendMessage(messageA);
    await chatPage.waitForResponse();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.selectSession(0);
    const messageB = `Session B message ${Date.now()}`;
    await chatPage.sendMessage(messageB);
    await chatPage.waitForResponse();

    await chatPage.selectSession(1);
    await page.waitForTimeout(500);
    await expect(
      page.getByText(messageA, { exact: false }).first()
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

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.selectSession(0);
    const messageKeep = `Keep this session ${Date.now()}`;
    await chatPage.sendMessage(messageKeep);
    await chatPage.waitForResponse();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.selectSession(0);
    const messageDelete = `Delete this session ${Date.now()}`;
    await chatPage.sendMessage(messageDelete);
    await chatPage.waitForResponse();

    const deleteTarget = page
      .locator("[data-testid^='chat-session-']")
      .first();
    const deletedId = await deleteTarget.getAttribute("data-testid");

    await chatPage.deleteSession();
    await page.waitForTimeout(1000);

    await expect(
      page.locator(`[data-testid='${deletedId}']`)
    ).not.toBeVisible({ timeout: 5000 });

    await chatPage.selectSession(0);
    await page.waitForTimeout(500);
    await expect(
      page.getByText(messageKeep, { exact: false }).first()
    ).toBeVisible();
  });

  test("new session starts with empty message history", async ({
    chatPage,
    page,
  }) => {
    await chatPage.goto();
    await chatPage.createSession();
    await page.waitForTimeout(500);

    await expect(
      page.getByText("no messages yet")
    ).toBeVisible({ timeout: 5000 });
  });

  test("chat history survives session switching", async ({
    chatPage,
    page,
  }) => {
    test.setTimeout(TIMEOUTS.chatStream);
    await chatPage.goto();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.selectSession(0);
    const message1 = `History survival test 1 ${Date.now()}`;
    await chatPage.sendMessage(message1);
    await chatPage.waitForResponse();

    await chatPage.createSession();
    await page.waitForTimeout(500);
    await chatPage.selectSession(0);
    const message2 = `History survival test 2 ${Date.now()}`;
    await chatPage.sendMessage(message2);
    await chatPage.waitForResponse();

    await chatPage.selectSession(1);
    await page.waitForTimeout(500);
    await expect(
      page.getByText(message1, { exact: false }).first()
    ).toBeVisible();
  });
});
