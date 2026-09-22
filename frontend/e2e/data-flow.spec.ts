import { expect, test } from "@playwright/test";

/**
 * Data-workbench E2E (FE-W4-S4): export (download event) → import (file input
 * re-ingest) → config form (save → `config-updated`). A workspace is seeded via
 * the HTTP API so this spec is independent of main-flow.spec.ts.
 *
 * Prerequisites: same as main-flow.spec.ts (built SPA + `api serve` on :8765).
 */

let workspaceId = "";

test.beforeAll(async ({ request }) => {
  const response = await request.post("/works", {
    data: {
      title: "E2E 数据流作品",
      genre: "测试",
      description: "数据工作台 E2E 种子作品",
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { id: string };
  workspaceId = body.id;
});

test("export downloads a ZIP, then import re-ingests the same archive", async ({
  page,
}) => {
  await page.goto(`/works/${workspaceId}/data`);
  await expect(page.getByTestId("data-page")).toBeVisible();

  // Export: trigger the browser download event for the ZIP.
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 ZIP" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.zip$/);

  // Import: feed the just-exported archive back through the file input.
  const archivePath = await download.path();
  await page.getByTestId("import-file-input").setInputFiles(archivePath);
  await page.getByRole("button", { name: "导入" }).click();
  await expect(page.getByTestId("import-result")).toBeVisible();
});

test("config form saves and shows config-updated", async ({ page }) => {
  await page.goto(`/works/${workspaceId}/data`);
  await expect(page.getByTestId("config-panel")).toBeVisible();

  // Default key is quality_threshold, rendered as a numeric text input.
  await page.getByPlaceholder("数值").fill("0.75");
  await page.getByRole("button", { name: "保存" }).click();
  await expect(page.getByTestId("config-updated")).toBeVisible();
});
