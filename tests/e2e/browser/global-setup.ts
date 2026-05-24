import { chromium, request } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = join(SCRIPT_DIR, ".auth");
const TOKEN_PATH = join(AUTH_DIR, "token.txt");
const STORAGE_STATE_PATH = join(AUTH_DIR, "session.json");

async function globalSetup(): Promise<void> {
  const token = readFileSync(TOKEN_PATH, "utf-8").trim();

  const apiContext = await request.newContext({
    baseURL: "http://127.0.0.1:8181",
    ignoreHTTPSErrors: true,
    extraHTTPHeaders: {
      Origin: "http://127.0.0.1:3100",
    },
  });

  const response = await apiContext.post("/api/v1/auth/exchange", {
    data: { token },
  });

  if (!response.ok()) {
    const body = await response.text();
    throw new Error(
      `Auth exchange failed (${response.status()}): ${body}`
    );
  }

  await apiContext.storageState({ path: STORAGE_STATE_PATH });
  await apiContext.dispose();

  const browser = await chromium.launch();
  const context = await browser.newContext({
    storageState: STORAGE_STATE_PATH,
    baseURL: "http://127.0.0.1:3100",
  });
  const page = await context.newPage();

  await page.goto("/");
  await page.waitForTimeout(2000);
  await page.getByText("e2e-test", { exact: false }).click();
  await page.waitForTimeout(2000);

  await context.storageState({ path: STORAGE_STATE_PATH });
  await browser.close();
}

export default globalSetup;
