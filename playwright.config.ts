import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    reducedMotion: "reduce",
  },
  // Run e2e against the production build. The Next dev server's HMR websocket can be
  // unavailable in some sandboxes, which blocks client hydration; `next start` does not
  // depend on it and reflects what the demo actually ships.
  webServer: [
    {
      command: "npm run dev:api",
      url: "http://127.0.0.1:8000/health/ready",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run build && npm run start",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 240_000,
    },
  ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
