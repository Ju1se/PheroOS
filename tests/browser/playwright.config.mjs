import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const port = Number(process.env.VISUAL_TEST_PORT || 8765);
const baseURL = process.env.VISUAL_BASE_URL || `http://127.0.0.1:${port}`;
const externalServer = Boolean(process.env.VISUAL_BASE_URL);
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.visual\.spec\.mjs/,
  timeout: 45_000,
  fullyParallel: false,
  reporter: [["list"]],
  outputDir: path.join(repoRoot, "output/playwright/test-results"),
  expect: {
    timeout: 8_000,
  },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: externalServer
    ? undefined
    : {
        command: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port ${port}`,
        cwd: repoRoot,
        url: `${baseURL}/health`,
        reuseExistingServer: true,
        timeout: 30_000,
      },
  projects: [
    {
      name: "desktop-chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
        colorScheme: "dark",
      },
    },
    {
      name: "mobile-chromium",
      use: {
        ...devices["Pixel 7"],
        colorScheme: "dark",
      },
    },
  ],
});
