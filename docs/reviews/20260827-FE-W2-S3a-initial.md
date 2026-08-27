# 2026-08-27 FE-W2-S3a 审查报告（初审查）

- 审查方式：codex exec review（独立 CLI，只读，flash/high）
- 审查范围：commit aeb998a（feat(frontend): add FE-W2 S3a overview multi-stream SSE feed）
- 审查依据：AGENTS.md / rules.md / frontend-app.md / docs/implementation/fe-w2-implementation.md / 13-frontend-app-checklist.md

### 优点

- 总览事件流改为每作品一条 SSE 订阅、客户端按 time 合并去重，useEventStream 新增 feature-agnostic 的 onEvent 回调；连接状态可见、断线重连、全局轮询兜底；既有三态与穿透 / 待拍板保留；前端四命令全绿（178 用例）。

### 问题

#### P3（可后补，均附复现测试）

1. 瞬时 /works 轮询失败把实时事件窗整体替换成错误态 — frontend/src/features/overview/useOverviewEventFeed.ts:183-184
   works.error 直接当事件窗 error，而 error 优先于 ready 渲染；任意一次 /works 轮询瞬时失败都会隐藏正在推送的实时事件（最长 3 秒才恢复）。修法：仅当 works.data === null 时上抛 works.error。
2. 已降级流在作品列表变化时被重新 attach，轮询兜底抖动 — frontend/src/hooks/useMultiEventStream.ts:120-125
   降级后从 sourcesRef 删除 id，attach 循环只看 sources.has(id)，ids 变化时降级流被重新 attach 成新 EventSource，degraded 翻转、/events 兜底被禁用，形成反复抖动。修法：维护已降级 id 的持久记录并跳过重新 attach。

### 结论

Ready to merge: With fixes（2 条 P3）

### 处理记录

- 2026-08-27 总监派 FE-W2-S3a-FIX，修复提交 c3618b0：error 仅在 works.data === null 时上抛（有数据时瞬时失败不覆盖 ready）；useMultiEventStream 增加 degradedIds 持久记录，attach 循环跳过已降级 id，卸载时清除；补三条回归测试（瞬时失败事件仍可见、ids 变化不重复 attach、id 移除再回来保持降级）。
- 2026-08-27 修复 c3618b0 由总监复核收口（diff 抽查 4 个范围内文件；前端四命令全绿，181 用例），审查链收敛，S3a 收口。
