import { expect, test } from "@playwright/test";

/**
 * Main-link E2E (FE-W4-S4): create a work, then walk the detail → talk →
 * writer → decision workbenches. All selectors use the `data-testid` hooks
 * already present in frontend/src/features.
 *
 * Prerequisites (run on a machine with a working backend + chromium):
 *   cd frontend && npm run build
 *   uv run novel-editorial api serve        # serves API + built SPA on :8765
 *   npx playwright install chromium
 */
test("create a work, then walk the talk, writer and decision workbenches", async ({
  page,
}) => {
  // ── Create work: overview → works list → create page ──
  await page.goto("/");
  await page.getByRole("link", { name: "作品与班子" }).click();
  await expect(page.getByTestId("works-page")).toBeVisible();
  await page.getByRole("link", { name: "创建作品" }).click();
  await expect(page.getByTestId("works-create-page")).toBeVisible();

  const title = `E2E 主链路 ${Date.now()}`;
  await page.getByTestId("works-title-input").fill(title);
  await page.getByTestId("works-submit-button").click();

  // ── Works detail ──
  await expect(page).toHaveURL(/\/works\/[^/]+$/);
  await expect(page.getByTestId("works-detail-page")).toBeVisible();
  await expect(page.getByTestId("header-workspace")).toContainText(title);

  // ── Talk workbench (sidebar nav) ──
  await page.getByRole("link", { name: "对话", exact: true }).click();
  await expect(page.getByTestId("talk-page")).toBeVisible();
  await page.getByTestId("talk-message-input").fill("给编辑部发第一句话");
  await expect(page.getByTestId("talk-send-button")).toBeEnabled();
  // Sending stores the author message and clears the input on success; agent
  // replies stream in over SSE and are not asserted here (LLM-dependent).
  await page.getByTestId("talk-send-button").click();
  await expect(page.getByTestId("talk-message-input")).toHaveValue("");

  // ── Writer workbench (sidebar nav) ──
  await page.getByRole("link", { name: "写作", exact: true }).click();
  await expect(page.getByTestId("writer-page")).toBeVisible();
  await page.getByTestId("new-draft-title").fill("第一章");
  await page.getByTestId("new-draft-submit").click();
  await expect(page.getByTestId("draft-editor")).toBeVisible();

  // ── Decision workbench (sidebar nav) ──
  await page.getByRole("link", { name: "拍板", exact: true }).click();
  await expect(page.getByTestId("decision-page")).toBeVisible();
  await expect(page.getByTestId("decision-panel")).toBeVisible();
});
