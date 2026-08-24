# 2026-08-25 FE-W1-S4a 审查报告（初审查）

- 审查方式：codex exec review（独立 CLI，只读，flash/high）
- 审查范围：commit ea0852e（feat(api): add draft version diff endpoint aligned with CLI (FE-W1 S4a)）
- 审查依据：AGENTS.md / rules.md / frontend-app.md / docs/implementation/fe-w1-implementation.md / 13-frontend-app-checklist.md

### 优点

- diff 端点复用 core.diff_versions，与 CLI draft diff 同源（v0 用法错误、缺版本 404、相同版本 no differences）；CLI/API 对照测试齐备；全量测试通过。

### 问题

#### P2（应该修）

1. OpenAPI 把 diff 响应声明成 application/json — src/novel_editorial/api/app.py:753-759
   端点实际返回 text/plain，但装饰器缺 response_class=PlainTextResponse，OpenAPI 把 200 声明为 application/json（空 schema），前端生成类型会把响应当 JSON，按契约消费会解析失败。修法：装饰器加 response_class 并重新生成快照与类型。

### 结论

Ready to merge: With fixes（1 条 P2）

### 处理记录

- 2026-08-25 总监派 FE-W1-S4a-FIX，修复提交 b0ea354：装饰器补 response_class=PlainTextResponse；新增 OpenAPI 契约断言（200 为 text/plain、非 application/json）；重新生成快照与 TS 类型。
- 2026-08-25 修复 b0ea354 由总监复核收口（diff 抽查 4 个范围内文件；全量 1487 测试 + ruff / pyright / 宪法 + gen:types 可复现全绿），审查链收敛，S4a 收口。
- 记录的后补项：inspect / workspace_log 两个 text/plain 端点同样缺 response_class，待统一补齐——已记入 docs/project-plan/07-parked-backlog.md。
