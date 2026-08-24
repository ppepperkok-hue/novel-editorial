# FE-W1 实施真元文档（前端大项目 · 里程碑 W1）

## 总览

- **大阶段**：前端独立大项目第一个里程碑 W1（立项 docs/project-plan/13-frontend-app-checklist.md，架构 docs/architecture/frontend-app.md）。
- **W1 一句话**：不敲 CLI，在界面完成一轮创作闭环——建作品 → 与编辑部对话 → 写 / 改正文 → 质量门 → 拍板。
- **现状**：frontend/ 面板 MVP（React 18 + Vite 6 + TypeScript，39 用例四命令绿）；N24 API 已有只读面 + decision 写面 + works 创建；无路由、无状态库、无 SSE。
- **验收总门**：前端四命令绿 + 后端 pytest / ruff / pyright 绿 + 契约对照测试（API 与 CLI 同源）+ W1 演示脚本（mock LLM 端到端）+ 独立审查归档 docs/reviews/。

## 红线（继承前端架构与立项，本阶段强制）

1. **前端只消费 API 契约**：不 import Python 包、不直连数据库、不复制业务逻辑。
2. **数据同源**：写面端点与 CLI 命令逐条映射，同源对照测试断言界面与 CLI 同一结果。
3. **失败显式化**：loading / empty / error 三态齐全；错误码与 CLI 对齐（业务 1 / 用法 2 / 系统 3），不静默吞错。
4. **最小改动**：不翻地基（技术栈 / 目录 / 事件契约 / 依赖方向），确需改先停下回报。

## 地基影响评估（先评估再动工）

- frontend/ 新增依赖：react-router-dom、@tanstack/react-query、zustand、react-markdown（运行期）；openapi-typescript（构建期生成类型）；package-lock 同步更新。
- 后端新增依赖：sse-starlette（SSE 实时通道）。
- src/novel_editorial/api/ 扩展写面端点 + OpenAPI；依赖方向 api → core 不变，业务仍下沉 core。
- events.py 事件契约不变（SSE 复用既有事件结构）；错误码枚举不变；不新增表、不迁移。
- S3 将涉及 DraftVersion 增加 actor 列（Alembic 加性迁移，作者改稿留痕）：本阶段 S1 不碰表结构与 core/draft，留到 S3 单独立评估。

## 子阶段 S1：后端契约与实时通道（FE-A）

### 做什么

- 写面端点（逐条映射**既有** CLI 命令，参数与错误码同源）：works 详情 / 班子 / 模板，talk send / list，draft generate / revise / list / show / diff，review add / list，decision list / pending / 三动作，style get / set。业务逻辑一律调 core 既有函数，不重写。
- OpenAPI 同步更新；openapi-typescript 生成 TS 类型进 frontend/src/api/（生成产物不手改）。
- SSE 端点 `/works/{workspace_id}/events/stream`：游标续传（Last-Event-ID = 该作品库 rowid，严格大于游标），payload 复用 events.py 契约；sse-starlette；断线重连语义与轮询降级（可配置）。

### 做到什么程度

- 每个写面端点与对应 CLI 命令同源（同参数、同错误码）；SSE 可订阅、可重连、降级可配。

### 验收标准

- 后端契约测试：每端点与 CLI 同源断言（同一数据双通道）；SSE 订阅 / 重连 / 降级测试；pytest / ruff / pyright 绿。

### 暂不做

- 前端工作台实现（S2–S4）；SSE 之外的双向机制；作者手动写作能力（新建空草稿 / 作者改稿落版本，需 DraftVersion.actor 迁移，S3 单独立评估）；全局事件流合并（W2）。

## 子阶段 S2：全功能壳与作品班子工作台（FE-B + FE-C）

### 做什么

- 面板 MVP 迁移并入：React Router 路由壳（侧栏 / 顶栏 / 工作台挂载位）、TanStack Query client、Zustand、三态组件基线；既有组件迁移并文档化。
- works 工作台：作品列表 / 详情 / 创建 / 模板 / 班子档案。

### 做到什么程度

- 既有 39 用例保持绿；打开即见路由壳，作品与班子全流程在界面可走。

### 验收标准

- 新组件三态测试；works 流程用例；前端四命令绿。

### 暂不做

- 对话 / 正文 / 拍板工作台（S3–S4）；结构 / 设定 / 总览（W2）。

## 子阶段 S3：对话与正文工作台（FE-D + FE-E）

### 做什么

- 对话工作台：talk 发送 / 回放、分歧 / 讨论标记（对齐 talk list 输出）。
- 正文工作台：纯文本 + Markdown 预览编辑器、手动保存、LLM 生成 / 修订接线、版本列表与对比、审稿意见显示、质量门结果与待拍板提示。
- 后端作者写作能力（本阶段落地）：core 作者存稿函数 + DraftVersion.actor 列 Alembic 加性迁移 + CLI `draft new` / `draft save` + 对应 API 端点；动工前先给影响评估（表结构为地基，评估后再实现）。

### 做到什么程度

- mock LLM 下端到端：发话 → 伙伴回应 → 生成 / 修订正文 → 版本可回看；界面与 CLI talk list 输出一致。

### 验收标准

- 对话与正文端到端用例（mock）；与 CLI 对照断言；前端四命令 + 后端三连绿。

### 暂不做

- 拍板动作（S4）；富文本编辑器（立项后置）。

## 子阶段 S4：拍板工作台与 W1 收口（FE-F）

### 做什么

- 待拍板清单 + accept / reject / note + 防误触确认；操作后界面与 CLI 同源可见。
- W1 演示脚本（mock 端到端可复现）+ 全量回归 + 前端四命令 + 独立审查归档。

### 做到什么程度

- 一轮创作闭环在界面完整走通；演示脚本干净环境可复现；审查链收敛 Ready。

### 验收标准

- 拍板用例 + 同源对照；演示脚本复跑通过；审查归档 docs/reviews/。

### 暂不做

- W2–W4 全部单元；Playwright E2E（W2 起引入）。

## 任务包规划（09a 文件不相交）

- 包 FE-W1-S1：src/novel_editorial/api/app.py + tests/test_api.py + pyproject.toml / uv.lock（sse-starlette）+ frontend/src/api 生成类型与 gen:types 脚本 + frontend/package.json / package-lock（openapi-typescript）+ docs/usage.md HTTP API 节。
- 包 FE-W1-S2：frontend/ 路由壳 + 状态库 + 三态基线 + works 工作台 + frontend 测试 + package.json / package-lock。
- 包 FE-W1-S3a：作者写作能力（store/models.py + migrations/ + core/draft.py + cli/draft.py + api 端点 + 后端测试 + OpenAPI 重生成）。
- 包 FE-W1-S3b：frontend/ talk + writer 工作台 + react-markdown + 测试（S3a 验收后再发）。
- 包 FE-W1-S4：frontend/ decision 工作台 + 演示脚本 + 回归 + 审查归档。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更；地基（技术栈 / 目录 / 事件契约 / 依赖方向）不动，确需改先停下评估。
- 每个子阶段完成即停，回报四段（做了什么 / 验证结果 / 偏离点 / 下一步建议），经总监确认后再进下一子阶段。

## 状态

- S1 完成（2026-08-25）：写面端点 + SSE 实时通道 + OpenAPI 生成类型，commits 74808cf / 2e676a9；全量 1464 测试 + ruff / pyright / 宪法 + 前端四命令全绿；独立审查 2 条 P3 已修复复核收敛，归档 docs/reviews/20260825-FE-W1-S1-initial.md。待办：S2（全功能壳与作品班子工作台）。
- S2 完成（2026-08-25）：路由壳（React Router / TanStack Query / Zustand）+ 三态基线 + works 工作台，commits 5150963 / e0bf264；前端 64 用例四命令全绿；独立审查 1 条 Important 已修复复核收敛，归档 docs/reviews/20260825-FE-W1-S2-initial.md。待办：S3（对话与正文工作台 + 作者写作能力）。
- S3a 完成（2026-08-25）：作者写作能力（DraftVersion.actor 迁移 + core 函数 + CLI draft new/save + API 端点），commits 487ee8f / 5ba4615；全量 1478 测试 + ruff / pyright / 宪法全绿；独立审查 1 条 Important 已修复复核收敛，归档 docs/reviews/20260825-FE-W1-S3a-initial.md。待办：S3b（前端对话与正文工作台）。
