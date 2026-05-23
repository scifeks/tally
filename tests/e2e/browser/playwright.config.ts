import { defineConfig } from "@playwright/test";

const API_PORT = 8181;
const VITE_PORT = 3100;

export default defineConfig({
  testDir: "./journeys",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["html", { open: "never" }], ["list"]],
  timeout: 60_000,

  use: {
    baseURL: `http://127.0.0.1:${VITE_PORT}`,
    storageState: ".auth/session.json",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  globalSetup: "./global-setup.ts",

  webServer: {
    command: `python start-tally.py --api-port ${API_PORT} --vite-port ${VITE_PORT}`,
    port: VITE_PORT,
    timeout: 30_000,
    reuseExistingServer: false,
    env: {
      BROWSER: "none",
    },
    stdout: "pipe",
    stderr: "pipe",
  },

  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
