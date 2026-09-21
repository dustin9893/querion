import { defineConfig } from "@playwright/test";

/**
 * Browser e2e against a live stack: web :3000, API :8000, worker + AI providers configured.
 *   npx playwright test            # headless
 *   npx playwright test --headed   # watch it
 * Screenshots land in e2e/screenshots/, traces in test-results/ on failure.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "e2e/report" }]],
  // Quay video demo: mỗi cảnh trong demo-video.spec.ts thành một .webm, ghép bằng scripts/demo-video.sh.
  // Tách thành project riêng để `npx playwright test` thường không quay video và không đụng bản deploy.
  projects: [
    { name: "default", testIgnore: /demo-video\.spec\.ts/ },
    {
      name: "video",
      testMatch: /demo-video\.spec\.ts/,
      use: {
        viewport: { width: 1600, height: 900 },
        video: { mode: "on", size: { width: 1600, height: 900 } },
        launchOptions: { args: ["--force-device-scale-factor=1", "--hide-scrollbars"] },
      },
    },
  ],
  // Mock bank website on two origins: 8090 is allow-listed by seed_demo, 8091 is not.
  webServer: [
    { command: "python3 -m http.server 8090 --bind 127.0.0.1 --directory ../../demo-site", url: "http://localhost:8090/index.html", reuseExistingServer: true, timeout: 15_000 },
    { command: "python3 -m http.server 8091 --bind 127.0.0.1 --directory ../../demo-site", url: "http://localhost:8091/index.html", reuseExistingServer: true, timeout: 15_000 },
    // an "intranet" page with no widget snippet at all — the browser extension must bring its own bubble
    { command: "python3 -m http.server 8092 --bind 127.0.0.1 --directory e2e/fixtures/intranet", url: "http://localhost:8092/index.html", reuseExistingServer: true, timeout: 15_000 },
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    viewport: { width: 1360, height: 900 },
    locale: "vi-VN",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
