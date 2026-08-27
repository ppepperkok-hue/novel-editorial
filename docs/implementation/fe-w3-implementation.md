# FE-W3 实施真元文档（前端大项目 · 里程碑 W3）

## 总览

- **大阶段**：前端大项目第三个里程碑 W3（立项 docs/project-plan/13-frontend-app-checklist.md，架构 docs/architecture/frontend-app.md）：质量风格工具区（FE-J）+ 自由意志可视化（FE-K）。
- **W3 一句话**：作者在界面用质量与风格工具打磨正文，并一眼看懂编辑部「为什么会这样」。
- **现状**：W1、W2 已收口（后端 1500 测试 + 前端 181 用例）；API 已有 style GET/POST、inspect、events/talk/structure 等；quality / style 工具（AI 味定位、漂移、好句、一致性、校准、试读反馈）与自由意志读面（动机、耐心、行为时间线、讨论）尚未铺 API。
- **验收总门**：后端 pytest / ruff / pyright 绿 + 前端四命令绿 + CLI/API 同源对照测试 + 演示脚本实跑 + 独立审查归档 docs/reviews/。

## 红线（继承 W1/W2，全阶段强制）

1. 前端只消费 API 契约，不复制业务逻辑。
2. 写面端点与 CLI 命令逐条映射，同源对照测试断言。
3. 三态齐全、错误码与 CLI 对齐，不静默吞错。
4. 最小改动：不翻地基（技术栈 / 目录 / 事件契约 / 表结构），确需改先停下评估。

## 地基影响评估

- 不新增表、不做迁移：质量 / 风格 / 自由意志全部复用既有 core 函数与事件；api → core 依赖方向不变；错误码与事件契约不变。
- 质量工具的输出以既有报告文本（text/plain 或结构化 payload）呈现，不新造结构。

## 子阶段 S1：后端契约（质量风格工具 + 自由意志读面）

### 做什么

- 逐条映射既有 CLI 命令的端点（先读 cli/quality.py、style.py、consistency.py、feedback.py、motives.py、patience.py、behavior.py、discussion 相关命令的签名与输出，业务一律调 core 既有函数）：
  - 质量：AI 味定位与改写建议、质量报告、好句识别与保留、一致性核查、语料校准、试读反馈回流。
  - 风格：风格锚点（已有 GET/POST）、文风参考学习、风格漂移检测。
  - 自由意志读面：动机列表、耐心池、行为时间线 / 当前状态、讨论 / 自然讨论记录。
- OpenAPI 更新 + npm run gen:types 重新生成；docs/usage.md HTTP API 节补端点说明。

### 验收标准

- 每端点与 CLI 同源对照测试；错误映射与 CLI 一致；pytest / ruff / pyright / 宪法绿。

### 暂不做

- 前端工作台（S2）；演示脚本与收口（S3）；全局合并 SSE（W2 已决策不做）。

## 子阶段 S2：质量风格工作台 + 自由意志可视化

### 做什么

- features/quality：风格锚点设置、AI 味定位 / 改写建议、好句、一致性报告、漂移检测、校准与试读反馈的图形呈现。
- features/freewill：动机、耐心池、行为时间线、讨论 / 自然讨论的可视化（时间线 + 状态卡），与 events / talk 同源。
- 三态齐全；与 CLI 同源；沿用现有设计体系与生成类型。

### 验收标准

- 前端四命令绿；mock 下质量工具与自由意志视图端到端用例；与 CLI 对照。

### 暂不做

- W4（数据管理与 Electron）全部单元；Playwright E2E。

## 子阶段 S3：演示脚本 + W3 收口

### 做什么

- W3 演示脚本（质量工具 + 自由意志可见，mock 端到端）；全量回归 + smoke_m3 + stress_m3 + 前端四命令 + 独立审查归档。

### 验收标准

- 演示脚本可复现；审查链收敛 Ready。

### 暂不做

- W4 全部单元。

## 任务包规划（09a 文件不相交）

- 包 FE-W3-S1：src/novel_editorial/api/app.py + tests/test_api.py + docs/usage.md + frontend/src/api 生成产物。
- 包 FE-W3-S2：frontend/ features/quality + features/freewill + 路由 + 测试。
- 包 FE-W3-S3：演示脚本 + 全量回归 + 审查归档 + 收口。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档；地基不动；每个子阶段完成即停、回报四段，经总监确认后再进下一子阶段。

## 状态

- S1 完成（2026-08-28）：质量（check / explain / calibrate / feedback）、风格（learn / drift）、一致性（check）、自由意志读面（motives / patience / behavior）十二个端点逐条映射 CLI，commit c4337c8；全量 1528 测试 + ruff / pyright / 宪法 + gen:types / typecheck 全绿；独立审查零问题收敛，归档 docs/reviews/20260828-FE-W3-S1-initial.md。待办：S2（质量风格工作台 + 自由意志可视化）。
- S2 完成（2026-08-28）：质量工作台（草稿选择 / 质量报告 / 风格学习与漂移 / 校准与试读反馈）+ 自由意志可视化（动机 / 耐心 / 行为时间线 / 状态），commits b60be12 / 841d2f8；前端 211 用例四命令全绿；独立审查 2 条 P3 已修复复核收敛，归档 docs/reviews/20260828-FE-W3-S2-initial.md。待办：S3（演示脚本 + 全量回归 + 审查归档 + W3 收口）。
