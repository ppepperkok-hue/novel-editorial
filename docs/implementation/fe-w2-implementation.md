# FE-W2 实施真元文档（前端大项目 · 里程碑 W2）

## 总览

- **大阶段**：前端大项目第二个里程碑 W2（立项 docs/project-plan/13-frontend-app-checklist.md，架构 docs/architecture/frontend-app.md）：结构 / 大纲（FE-G）+ 设定 / 知识 / 灵感 / 检索（FE-H）+ 跨作品总览与 SSE 实时事件流（FE-I）。
- **W2 一句话**：作者在界面管作品骨架与信息层，并在总览实时看见编辑部动静。
- **现状**：W1 已收口（后端 1487 测试 + 前端 120 用例；四个工作台 + SSE 客户端）；API 已有 structure 只读面与 inspect 穿透；structure / outline / setting / inspiration 的写面尚未铺。
- **验收总门**：后端 pytest / ruff / pyright 绿 + 前端四命令绿 + CLI/API 同源对照测试 + 总览 SSE 实时实跑 + 独立审查归档 docs/reviews/。

## 红线（继承 W1，全阶段强制）

1. 前端只消费 API 契约，不复制业务逻辑。
2. 写面端点与 CLI 命令逐条映射，同源对照测试断言。
3. 三态齐全、错误码与 CLI 对齐，不静默吞错。
4. 最小改动：不翻地基（技术栈 / 目录 / 事件契约 / 表结构），确需改先停下评估。

## 地基影响评估

- 不新增表、不做迁移：结构 / 大纲 / 设定 / 灵感复用既有表与 core 函数；api → core 依赖方向不变；events.py 契约与错误码不变。
- 全局实时事件流：跨作品事件在各作品库独立存储（rowid 不可跨库比较），**决策**——总览页对每部作品各开一条 `/works/{id}/events/stream` 订阅并在客户端合并（按事件 time 排序），后端不做全局合并 SSE（避免跨库游标复杂化）。单作品工作台继续用既有 SSE 客户端。

## 子阶段 S1：后端写面（结构 / 大纲 / 设定 / 灵感）

### 做什么

- 逐条映射既有 CLI 命令的写面与读面端点：structure（add / rename / move / remove / status / list）、outline（create / revise / show）、setting（add / revise / list / check / show）、inspiration（add / list / show / remove）；业务一律调 core 既有函数，参数与错误码同 CLI。
- OpenAPI 更新 + npm run gen:types 重新生成；docs/usage.md HTTP API 节补端点说明。

### 验收标准

- 每端点与 CLI 同源对照测试；空/非法/不存在参数的错误映射与 CLI 一致；pytest / ruff / pyright / 宪法绿。

### 暂不做

- 前端工作台（S2）；总览 SSE 合并接线（S3）；memory notes / plot / knowledge 独立管理面（后补清单再议，不在 W2 最小面）。

## 子阶段 S2：结构 / 大纲 / 设定 / 灵感工作台

### 做什么

- features/structure：卷章篇树（增改移删、状态、大纲）+ 进度显示；features/settings：设定库（人物/世界观/情节线等 kind，增改查 + check 报告）+ 灵感素材（增删查）+ 穿透检索（inspect）。
- 三态齐全；与 CLI 同源；沿用现有设计体系与生成类型。

### 验收标准

- 前端四命令绿；mock 下结构 / 设定 / 灵感主链路端到端用例；与 CLI 对照。

### 暂不做

- 质量风格工具与自由意志可视化（W3）；SSE 总览（S3）。

## 子阶段 S3：总览 SSE 合并 + W2 收口

### 做什么

- 总览页对每部作品订阅 `/works/{id}/events/stream`，客户端按事件 time 合并渲染；连接状态可见、断线重连、轮询降级沿用 useEventStream；单作品页继续用既有接线。
- W2 演示脚本扩展或新增（结构 → 设定 → 灵感 → 事件实时可见）；全量回归 + smoke_m3 + stress_m3 + 前端四命令 + 独立审查归档。

### 验收标准

- 总览实时事件实跑（写入事件后数秒内界面出现）；演示脚本可复现；审查链收敛 Ready。

### 暂不做

- W3（质量与自由意志可视化）、W4（数据管理与 Electron）全部单元；Playwright E2E。

## 任务包规划（09a 文件不相交）

- 包 FE-W2-S1：src/novel_editorial/api/app.py + tests/test_api.py + docs/usage.md + frontend/src/api 生成产物。
- 包 FE-W2-S2：frontend/ features/structure + features/settings + 路由 + 测试。
- 包 FE-W2-S3：frontend/ 总览 SSE 合并 + 演示脚本 + 全量回归 + 审查归档。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档；地基不动；每个子阶段完成即停、回报四段，经总监确认后再进下一子阶段。

## 状态

- S1 完成（2026-08-25）：结构 / 大纲 / 设定 / 灵感写面与读面端点（逐条映射 CLI），commits a86d96e / 69d2b6a；全量 1500 测试 + ruff / pyright / 宪法 + gen:types / typecheck 全绿；独立审查 1 条 P3 已修复复核收敛，归档 docs/reviews/20260825-FE-W2-S1-initial.md。待办：S2（结构 / 大纲 / 设定 / 灵感工作台）。
- S2 完成（2026-08-25）：结构工作台（卷章篇树 / 大纲 / 进度）+ 设定与灵感工作台（设定库 / check 报告 / 灵感素材 / 穿透检索），commits 1cab0c7 / 6a8aeb5；前端 160 用例四命令全绿；独立审查 2 条 P3 已修复复核收敛，归档 docs/reviews/20260825-FE-W2-S2-initial.md。待办：S3（总览 SSE 合并 + W2 收口）。
- S3a 完成（2026-08-27）：总览多流 SSE 实时事件流（每作品一条订阅、客户端合并去重、断线重连、全局轮询兜底），commits aeb998a / c3618b0；前端 181 用例四命令全绿；独立审查 2 条 P3 已修复复核收敛，归档 docs/reviews/20260827-FE-W2-S3a-initial.md。待办：S3b（演示脚本 + 全量回归 + 审查归档 + W2 收口）。
- S3b 完成（2026-08-27）：W2 演示脚本（mock 端到端）+ 全量收口回归 + 归档，commit 0aacbc2；后端 1500 测试 + smoke_m3 + stress_m3 + ruff / pyright / 宪法 + 前端 181 用例四命令全绿；归档 docs/reviews/20260827-FE-W2-S3b-initial.md。**W2 完成**（结构 / 大纲 / 设定 / 灵感工作台 + 总览 SSE 实时事件流）。下一步：W3（质量风格工具与自由意志可视化）。
