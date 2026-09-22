# FE-W4 S4 Pre-flight 清单（FE-M 设计打磨与 QA）

静态核对基于 `frontend/src` 源码逐页抽查；「需浏览器验证」项只标注、不在沙箱断言。

## 核对结论速览

| 核对项 | 结论 |
| --- | --- |
| 三态（loading / error / success） | ✅ 通过（静态） |
| 错误处理：写操作失败 `role="alert"` | ⚠️ 部分通过（2 个 feature 有缺口，见 §2） |
| 可访问性（导航 / 按钮 / 输入） | ✅ 通过（静态抽查） |
| 键盘操作（表单 onSubmit / 按钮 type） | ✅ 通过（静态） |
| 文案一致（CLI ↔ UI） | ✅ 通过（静态） |
| 主题 / 响应式 | 🔍 需浏览器渲染验证 |

## 1. 三态（loading / error / success）

共享组件 `frontend/src/components/StateViews.tsx`：`SkeletonRows`（`data-testid="panel-state-loading"` + `aria-busy`）、`EmptyState`（`panel-state-empty`）、`ErrorState`（`panel-state-error` + `role="alert"` + 重试按钮）。

| feature | loading | error | empty / success |
| --- | --- | --- | --- |
| Overview | PanelWindow | PanelWindow→ErrorState | EmptyState / ready |
| WorksListPage | SkeletonRows | ErrorState | EmptyState / works-grid |
| WorksCreatePage | SkeletonRows | ErrorState | EmptyState / template-list |
| WorksDetailPage | SkeletonRows | ErrorState | works-overview + band |
| TalkPage | SkeletonRows | ErrorState | EmptyState / talk-list |
| WriterPage | SkeletonRows | ErrorState | EmptyState / workbench |
| DecisionPage | SkeletonRows | ErrorState | EmptyState / pending-list |
| DataPage | SkeletonRows | ErrorState | config-snapshot |

结论：各 feature 三态齐全，共用组件无散落实现。**通过**。

## 2. 错误处理（写操作失败内联 `role="alert"`）

✅ 已带 `role="alert"`：WorksCreatePage（`works-create-error`）、DataPage 导出 / 导入 / 配置（3 处）、PendingDraftItem（`pending-error`）、SettingsPage（5 处）、StructurePage（3 处）、QualityPage、FreewillPage、StateViews 的 ErrorState。

❌ 缺 `role="alert"`（静态发现，需后续修复；本包不碰 `frontend/src`）：

- `TalkPage.tsx` — `talk-send-error`（第 157 行）
- `WriterPage.tsx` — `save-error` / `revise-error` / `new-draft-error` / `generate-error`（第 211 / 297 / 653 / 658 行）

结论：**部分通过**，Talk 与 Writer 两条写链路的失败提示未用 `role="alert"` 标记，屏幕阅读器不会主动播报；建议在下一包补 `role="alert"`。

## 3. 可访问性

- 导航 `aria-label`：App 侧栏 `aria-label="工作台"`；作品详情 `aria-label="工作台入口"`。✅
- 输入标注：WorksCreate 三个输入均带 `aria-label` + `placeholder`；Talk 文本域用 `<label htmlFor>`；Writer 正文 `textarea` 带 `aria-label="正文内容"`；Data 导入 `file input` 带 `aria-label="选择 ZIP 文件"`；Data 配置键 / 值用 `<label>` 包裹。✅
- 按钮文案：创建作品 / 发送 / 新建空稿 / 生成草稿 / 手动保存 / 生成修订版 / 接受 / 拒绝 / 指示 / 导出 ZIP / 导入 / 保存——均有可见文案。✅

结论：**通过（静态抽查）**。

## 4. 键盘操作

- 表单提交走 `form onSubmit`：WorksCreate、Talk、Writer 新建 / 生成、Data 配置。✅
- 按钮 `type` 正确：表单提交按钮 `type="submit"`；动作按钮（手动保存 / 生成修订版 / 导出 / 导入 / 接受 / 拒绝）`type="button"`。✅

结论：**通过（静态）**。

## 5. 文案一致（CLI ↔ UI）

| 概念 | UI 文案 | CLI / API |
| --- | --- | --- |
| 导出 | 导出 ZIP / 导出失败 | `works export` / `GET /works/{id}/export` |
| 导入 | 导入 / 导入失败 / 已导入作品 | `works import` / `POST /works/import` |
| 配置 | 配置 / 保存 / 保存失败 | `PUT /config` / CLI `--apply` |
| 拍板 | 拍板 / 接受 / 拒绝 / 指示 | `decision` 三动作 |
| 创建 | 创建作品 | `works create` |

结论：**通过（静态）**。

## 6. 主题 / 响应式

🔍 **需浏览器渲染验证**：布局断点、深 / 浅主题、Skeleton 占位与真实内容高度一致性，均需在 Windows 实机浏览器里人工核对，沙箱不做断言。

## 本沙箱静态核对通过项

- Playwright 配置、两个 spec、pre-flight 清单均落盘。
- 三态（SkeletonRows / ErrorState / EmptyState / success）各 feature 齐全。
- 多数写操作失败提示带 `role="alert"`。
- 导航 / 输入 / 按钮的可访问性标注齐全。
- 表单 `onSubmit` + 按钮 `type` 正确。
- CLI 与 UI 用语一致（导出 / 导入 / 配置 / 拍板 / 创建）。
- `npm run typecheck` 覆盖 e2e 目录与 playwright.config.ts（tsconfig include 已扩展）。
- `npm run lint` 覆盖 e2e 目录（eslint.config.js 未忽略 e2e）。

## 需 Windows 实机浏览器验证项

- `npx playwright install chromium`：沙箱下载浏览器二进制受限，未执行；需实机安装。
- `npm run test:e2e`：需实机先 `npm run build` + `uv run novel-editorial api serve`（同源托管于 `http://127.0.0.1:8765`）后实跑。
- Talk 发送后输入框清空、Writer 建稿、Data 导出下载 / 导入回灌 / 配置保存，均依赖真实后端与（Talk 链路的）LLM 配置。
- 主题 / 响应式的渲染效果。
- 上述 §2 中 Talk / Writer 内联错误补 `role="alert"` 后的回归验证。

## 偏离与备注

- `frontend/tsconfig.json` 的 `include` 由 `["src"]` 扩展为 `["src", "e2e", "playwright.config.ts"]`，以便 `npm run typecheck` 真正编译 e2e 目录（任务包「除非 e2e 需要 include」条款）。
- 未触碰 `frontend/src` 业务代码；Talk / Writer 内联错误缺 `role="alert"` 仅记录，不在本包修复。
