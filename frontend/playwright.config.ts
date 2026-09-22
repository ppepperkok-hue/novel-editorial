import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration (FE-M / FE-W4-S4).
 *
 * The backend `uv run novel-editorial api serve` hosts BOTH the built frontend
 * (frontend/dist) and the HTTP API on the same origin at http://127.0.0.1:8765,
 * so `baseURL` points there and no `webServer` is configured — start the server
 * manually before running the suite:
 *
 *   cd frontend && npm run build            # produce frontend/dist
 *   uv run novel-editorial api serve        # API + SPA on :8765
 *   npx playwright install chromium         # once, on a machine with CDN access
 *   npm run test:e2e
 */
export default defineConfig({
  testDir: "./e2e",
  reporter: "list",
  // The backend migration path is serialized (store/db.py `_migration_lock`),
  // so specs can run in parallel again.
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:8765",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
