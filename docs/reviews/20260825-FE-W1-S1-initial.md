# 2026-08-25 FE-W1-S1 审查报告（初审查）

- 审查方式：codex exec review（独立 CLI，只读，flash/high）
- 审查范围：commit 74808cf（feat(api): add FE-W1 S1 write endpoints, SSE stream and generated TS types）
- 审查依据：AGENTS.md / rules.md / frontend-app.md / docs/implementation/fe-w1-implementation.md / 13-frontend-app-checklist.md

### 优点

- 全量测试与新增测试通过，lint / 类型检查 / 前端构建干净，OpenAPI 快照与生成类型最新；新端点复用 core / CLI 既有逻辑，契约对齐（含 CLI 与 API 同源对照测试）。

### 问题

#### P3（不阻塞）

1. SSE 流在事件循环里做同步 DB 轮询 — src/novel_editorial/api/app.py:485-492
   `_event_stream` 每秒直接用同步 `list_events_since` 查库，慢查询或瞬时锁会卡住整个 uvicorn 事件循环与 sse-starlette 心跳。影响：连接多时互相拖累。修法：把查询移出事件循环（anyio.to_thread.run_sync 或 run_in_executor）。
2. 空消息通过校验仍调 LLM — src/novel_editorial/api/app.py:117-118
   `TalkSendBody.message` 无 min_length / 非空白检查，空消息会落库并触发一次退化的 LLM 调用；`ReviewAddBody.content` 同理可存空意见。修法：与 CreateWorkspaceBody.title 等一致，拒绝空白输入。

### 结论

Ready to merge: With fixes（2 条 P3，不阻塞）

### 处理记录

- 2026-08-25 总监派 FE-W1-S1-FIX，修复提交 2e676a9：SSE 查询用 asyncio.to_thread 移出事件循环（游标语义与心跳不变）；message / content 加 min_length=1 与 field_validator 拒绝空白，返回 422；新增空白消息 / 空白意见 / 慢查询不卡健康检查三条回归测试；OpenAPI 快照同步刷新。
- 2026-08-25 修复 2e676a9 由总监复核收口：受影响测试 + 全量 1464 + ruff / pyright / 宪法 + 前端四命令全绿；审查链收敛，S1 收口。
- 记录的后补项：API 对空白消息比 CLI 严（CLI talk send 待同步为用法错误）；API 层 talk / draft 编排胶水与 cli 层重复（待 S3 动 core 时合并下沉）——两条已记入 docs/project-plan/07-parked-backlog.md。
