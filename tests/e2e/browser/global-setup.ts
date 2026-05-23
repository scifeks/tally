import { request } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const AUTH_DIR = join(SCRIPT_DIR, ".auth");
const TOKEN_PATH = join(AUTH_DIR, "token.txt");
const STORAGE_STATE_PATH = join(AUTH_DIR, "session.json");

async function globalSetup(): Promise<void> {
  const token = readFileSync(TOKEN_PATH, "utf-8").trim();

  const context = await request.newContext({
    baseURL: "http://127.0.0.1:3100",
    ignoreHTTPSErrors: true,
  });

  const response = await context.post("/api/v1/auth/exchange", {
    data: { token },
  });

  if (!response.ok()) {
    const body = await response.text();
    throw new Error(`Auth exchange failed (${response.status()}): ${body}`);
  }

  await context.storageState({ path: STORAGE_STATE_PATH });
  await context.dispose();
}

export default globalSetup;
