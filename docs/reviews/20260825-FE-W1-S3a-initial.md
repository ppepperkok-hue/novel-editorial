# 2026-08-25 FE-W1-S3a 审查报告（初审查）

- 审查方式：codex exec review（独立 CLI，只读，flash/high）
- 审查范围：commit 487ee8f（feat(draft): add author writing capability with actor migration (FE-W1 S3a)）
- 审查依据：AGENTS.md / rules.md / frontend-app.md / docs/implementation/fe-w1-implementation.md / 13-frontend-app-checklist.md

### 优点

- DraftVersion.actor 加性迁移带幂等回填（写手名 / 空串、重放不覆盖作者行）；core 作者写作函数复用既有质量门与事件；CLI 与 API 同源；全量 1477 测试通过，迁移实测覆盖旧库重放。

### 问题

#### Important（应该修）

1. v0 作者空稿破坏 draft show / diff / revise 路径 — src/novel_editorial/core/draft.py:278-299
   create_author_draft 产生 current_version=0 且无 DraftVersion 行的草稿，但 draft show / diff / revise_draft 都假设 v>=1：draft new 后立即 show 抛 draft version not found v0（退出码 1），API revise 返回 404。影响：v0 状态是主流程可直达的，会直接报错。修法：版本读取处对 v0 做守卫（show 输出「暂无内容」；diff / revise 报用法错误）。

### 结论

Ready to merge: With fixes（1 条 Important）

### 处理记录

- 2026-08-25 总监派 FE-W1-S3a-FIX，修复提交 5ba4615：revise_draft 对 v0 在调 LLM 前抛 USAGE_ERROR（API 422）；draft show 对 v0 输出「暂无内容」退出码 0；draft diff 对无版本草稿报用法错误；补回归测试与 usage.md 边界说明。
- 2026-08-25 修复 5ba4615 由总监复核收口（diff 抽查 5 个范围内文件；全量 1478 测试 + ruff / pyright / 宪法全绿），审查链收敛，S3a 收口。
- 记录的后补项：draft list / show 对 writer_id 为空的作者稿仍回退显示默认写手名（应显示「作者」）——已记入 docs/project-plan/07-parked-backlog.md。
