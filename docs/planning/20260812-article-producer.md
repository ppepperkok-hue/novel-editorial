# 通用文章产出器 · 决策记录与工程表

> 日期：2026-08-12
> 状态：实施中（老板已确认方向：工作日泛化后接入第二个产出器）
> 前置：`20260812-generalization-decision.md`（v3）、`dd6c05d`（workday/提示词泛化）

## 1. 目标与验收

**目标**：注册第二个产出器「article（通用文章）」，验证 `settings.workday_producer` 一键切换产出链；网文产出器零改动。

**验收**：
1. `settings.workday_producer='article'` 时，workday open 走 article 产出器；缺省仍为 novel。
2. article 产出链：策划大纲 → 写正文 → 润色 → 审稿 → 落盘 markdown；dry-run 全链占位。
3. 输出目录 `settings.article_output_dir` 可配置，默认 `exports/articles/`。
4. 504 全量回归全绿；新增 article 产出器测试。
5. 网文产出器（novel）行为不变。

## 2. 设计

- 新模块 `tools/produce_article.py`：`produce_article(conn, *, target, trigger, dry_run, db_path, workday_run_id, lock_held, skip_diaries, boss_instruction="", plan=None)`。
- 主题来源：`boss_instruction`（老板指令）优先，其次 `plan.focus`；都没有则用默认主题「自由写作」。
- 链：planner（内容策划，产出主题/结构）→ writer（正文，通用任务段）→ editor（润色）→ reviewer（审稿 JSON）→ 落盘。
- 落盘：`exports/articles/<YYYYMMDD-HHMMSS>-<slug>.md`，含标题、正文、审稿摘要；dry-run 不落盘。
- LLM 调用全部走 `agent_tool_loop.run`（知识工具/人物档案自动注入）；dry-run 用占位文本。
- `producers.py` 注册 `"article": produce_article`；`workday.open/resume` 调用 `run_producer` 时透传 `boss_instruction` 与 `plan`。

## 3. 工程表

| 步骤 | 改动 | 验收 |
| --- | --- | --- |
| 1 | `tools/produce_article.py` 产出链实现 | dry-run 全链占位；真实（mock）产出 markdown |
| 2 | `producers.py` 注册 article | `run_producer("article", ...)` 可用 |
| 3 | `workday.py` 透传 boss_instruction/plan 给产出器 | article 产出器拿到主题 |
| 4 | `app_settings` 默认值加 `article_output_dir` | 配置读取生效 |
| 5 | `tests/test_produce_article.py`（mock LLM） | 落盘断言 + 网文回归 |
| 6 | 全量回归 + dry-run 验证 | 504 全绿；workday write 模式默认仍 novel |

## 4. 风险

- 提示词契约：article 产出器不依赖 editorial_daily 的解析，writer 只输出正文、reviewer 输出 JSON，与既有契约兼容。
- 落盘安全：slug 清洗（去路径危险字符），目录自动创建。
- 可回退：独立提交；`workday_producer` 缺省 novel，切回即恢复网文链。
