# 2026-08-28 FE-W3-S3 审查报告

- 审查方式：codex exec review（独立 CLI，只读）
- 审查范围：commit 140fd56（scripts/w3_demo.py + docs/usage.md）
- 审查依据：AGENTS.md / docs/architecture/rules.md / docs/implementation/fe-w3-implementation.md

## 优点

- 演示脚本与 w1/w2_demo 结构一致：幂等临时目录、mock LLM、TestClient 不启端口、每步 require 断言、失败立即 DEMO FAILED。
- 覆盖 W3 全链路：风格锚点回读、作者稿保存、质量 check/explain、一致性、风格 learn/drift、校准、试读反馈、动机/耐心/行为时间线/状态，断言与当前 API 响应吻合。
- usage.md 补句位置与段落习惯一致；calibrate/feedback 全程 apply=False，不碰仓库配置。

## 问题

### Minor（可后补）

- scripts/w3_demo.py:43-49 `_prepare_env` 只清 `NOVEL_LLM_*`，调用方 shell 的其它 `NOVEL_*`（如 `NOVEL_QUALITY_THRESHOLD`）会漏入 demo，改变质量门结果甚至让 load_settings 裸崩，违背 docstring 的 self-contained 承诺。影响：开发者恰好设了阈值变量时 demo 误报失败；默认环境与既有测试不受影响。修法：先清全部 `NOVEL_*`，再设 `NOVEL_DATA_DIR` / `NOVEL_CONFIG`。

## 结论

Ready to merge: With fixes

## 处理记录

- 核实：复现 `NOVEL_QUALITY_THRESHOLD=0` 时 PUT 正文返回 quality_failed、DEMO FAILED，属实。
- 修复：commit d93c57d（fix(demo): isolate FE-W3 S3 demo from caller NOVEL_* environment），只动 scripts/w3_demo.py。
- 复核：独立审查 CLI 复审 d93c57d——清后设顺序安全、load_settings/create_app 在 _prepare_env 之后才读环境、带泄漏变量与 uv run 两种跑法均 DEMO OK，无回归。
- 状态：Ready。附带跟进：w1_demo.py / w2_demo.py / panel_demo.py 存在同类泄漏模式，已列入 docs/project-plan/07-parked-backlog.md P3。
