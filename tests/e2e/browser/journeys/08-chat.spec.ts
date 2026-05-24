import { test, expect } from "../fixtures/base";
import { TIMEOUTS } from "../fixtures/constants";

test.describe.serial("Journey 8: Chat", () => {
  test("navigates to chat page", async ({ chatPage, page }) => {
    await chatPage.goto();
    await expect(page).toHaveURL(/\/chat/);
  });

  test("creates a new chat session", async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.createSession();
    await chatPage.expectSessionCount(1);
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

  test("creates a second session", async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.createSession();
    await chatPage.expectSessionCount(2);
  });

  test("switches between sessions", async ({ chatPage, page }) => {
    await chatPage.goto();
    await chatPage.selectSession(0);
    await page.waitForTimeout(500);
    await chatPage.selectSession(1);
    await page.waitForTimeout(500);
    await expect(
      page.getByText("SESSION", { exact: false })
    ).toBeVisible();
  });

  test("deletes a session", async ({ chatPage }) => {
    await chatPage.goto();
    await chatPage.deleteSession();
    await chatPage.expectSessionCount(1);
  });
});
