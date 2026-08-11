审查范围：prompts/ 目录与 tools/ 下 6 个知识相关工具（novel_knowledge / knowledge_keeper / distill_lessons / clean_novel_knowledge / ai_taste_check / export_agent_prompts），仅读取 db/config/services/llm_client 契约。基线：python -m compileall 全部通过；slice 定向测试 22 passed（test_novel_knowledge / test_clean_knowledge / test_knowledge_keeper / test_distill_lessons / test_knowledge_bible）；CLI 冒烟 knowledge_keeper --dry-run、export_agent_prompts、ai_taste_check 正常，distill_lessons 因环境无 API key 按预期失败。结论：存在 1 个 P1（每日自动同步造成 version/history 持续膨胀，已由 demo.db 数据证实）与 4 个 P2（clean 工具两类外键崩溃、知识管家静默失败、updated_at 不刷新），均需修复后才能视为正确。

Full review comments:

- [P1] 重复同步章节摘要导致 version/history 无限膨胀 — E:\code\novel-editorial\tools\novel_knowledge.py:195-208
  `tools/novel_knowledge.py` 的 `sync_from_chapters` 调用 `upsert_ex`，后者在行已存在时无条件插入 `novel_knowledge_history` 并 `version=version+1`（第 195-208 行），不比对内容是否变化。复现：对同一章节摘要连续运行 3 次 `sync_from_chapters`，内容未变但 `version` 从 1 涨到 3、history 增加 2 条重复记录；demo.db 中 knowledge_id=11 已有 12 条 history 即此现象。`editorial_daily.py:1304` 每天 wrap-up 都调用 `sync_latest`，每次运行都会给最近 3 章的角色/事件/时间线各 +1 version、+1 条 history。后果：version 失真（agent 工具展示 `v{n}` 误导决策）、history 表持续膨胀、updated_at 每次刷新。bible 同步路径的 `_upsert_if_changed` 有内容比对，章节路径缺失，应复用同样逻辑。

- [P2] clean_novel_knowledge 删除带 history 的 power/金手指 行触发外键崩溃 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:209-214
  `apply_clean` 的 golden_finger_dups 分支（`tools/clean_novel_knowledge.py:209-214`）在 `keep_id` 为 None 时直接 `DELETE FROM novel_knowledge WHERE id=?`，未先清理 `novel_knowledge_history`。`db.connect` 开启 `PRAGMA foreign_keys=ON` 且 `novel_knowledge_history.knowledge_id REFERENCES novel_knowledge(id)`，行存在 history 时删除抛 `IntegrityError`。复现：构造 power/金手指 行 + 1 条 history、无 item/金手指 → apply 崩溃。该工具唯一用途就是清理这类遗留数据，目标场景直接失败且整个事务回滚（--apply 静默无效）。

- [P2] 链式相似规则合并计划引用已删除行导致 --apply 崩溃 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:127-141
  `_plan_similar_rules`（`tools/clean_novel_knowledge.py:127-141`）对每对相似规则独立生成计划项、不做传递去重。当 A~B、B~C、A~C 两两相似（如"五行相生相克/五行相生相克法则/五行相生相克关系"）时生成 3 项；apply 先删 B，随后处理 keep=B 的项时 `UPDATE novel_knowledge_history SET knowledge_id=B` 引用已删除行 → `IntegrityError`。复现：3 行链式数据 plan 生成 3 项、apply 抛 FOREIGN KEY constraint failed。真实规则库（32 条 world_rule）中"阴阳守恒/阴阳守恒之律"这类相似名很可能出现链式。修复需在 apply 时跳过 keep 已不存在的项或 plan 阶段去重。

- [P2] 模型输出非 JSON 时知识管家静默成功（fake green） — E:\code\novel-editorial\tools\knowledge_keeper.py:135-160
  `knowledge_keeper.run()` 中 `parsed = _parse_json(text) or {}`（`tools/knowledge_keeper.py:135`）把解析失败吞成空 dict，随后各循环全部空转，返回 `{"ok": True, "auto_updates": [], ...}` 并写入 keeper_run 审计。复现：mock `chat_deepseek` 返回"抱歉，我无法完成" → ok=True、全空、audit 1 条。与 `distill_lessons.py` 的显式 `ok=False, error="distill output was not JSON"` 处理不一致，调度器与监控会误以为维护成功，实际什么都没做。

- [P2] 知识包自动更新后 frontmatter updated_at 不刷新 — E:\code\novel-editorial\tools\knowledge_keeper.py:176-176
  `knowledge_keeper.run()` 把 `dict(full["meta"])`（含旧 updated_at）传给 `knowledge.write_knowledge`，而后者用 `meta.setdefault("updated_at", now)`（`novel_editorial/services/knowledge.py:77`）只在缺失时设置。复现：对 market-and-reader.md 执行与 run() 相同的写回流程，updated_at 仍为 '2026-08-10'。知识管家的职责是"知识包必须新鲜"，但自动更新后时效戳与 audit detail 都停留在旧值，面板排序与后续时效判断无法识别包已被更新。修复应在写回前显式 `meta["updated_at"] = now`。

- [P3] ai_taste_check 漏检全角问号连续与全角叹问组合 — E:\code\novel-editorial\tools\ai_taste_check.py:34-34
  `EXCLAMATION_PATTERN`（`tools/ai_taste_check.py:34`）只覆盖 `！！`、`??`、`！?`、`？!`，漏掉 `？？` 与 `？！`，而 `prompts/knowledge/anti-ai-style.md` 硬规则明确"禁止？？和！！"。复现：`EXCLAMATION_PATTERN.findall("你说什么？？")` 返回空，含 4 处连续全角问号的文本 score=0、notes 为空，与知识包硬规则直接矛盾。

- [P3] novel_knowledge 死参数与 CLI 文档不一致 — E:\code\novel-editorial\tools\novel_knowledge.py:365-365
  `sync_from_chapters(conn, novel_id, chapter_id=None, ...)`（`tools/novel_knowledge.py:365`）的 `chapter_id` 参数从未使用，而 CLI `--sync N` 传入的实为 novel_id（参数名误导维护者）；`_add_conflict_draft` 的 `novel_id`/`category` 参数也未使用（第 108 行）；模块 docstring 写 `--snapshot --novel-id 1` 但 argparse 实际是 `--snapshot 1`。属维护性问题，建议删除死参数并修正文档。

- [P3] prompts/ 根目录四个旧模板为死文件 — E:\code\novel-editorial\prompts\editor.md:1-1
  `prompts/editor.md`、`memory.md`、`reviewer.md`、`writer.md` 未被任何代码引用（rg 全仓确认），实际提示词资产在 `prompts/agents/`，根目录 writer.md 还残留 `{min_chars}/{chapter_outline}` 占位符。易被误改或与 prompts/agents 同名文件混淆，建议删除或标注 deprecated。

- [P3] export_agent_prompts 导出 frontmatter 丢失 max_tokens — E:\code\novel-editorial\tools\export_agent_prompts.py:72-76
  `tools/export_agent_prompts.py:72-76` 导出 frontmatter 只写 model/temperature，而实际资产（如 prompts/agents/writer.md）含 `max_tokens: 4000`，`render_workflow.parse_asset` 会读取该字段。当前工作流为 PROXY_MODE 时脚本直接返回（no-op），但若回切非 proxy 模式，export→render 往返会静默丢失 max_tokens，影响生成长度控制。

- [P3] distill_lessons 对 topics/attendees 脏 JSON 无保护 — E:\code\novel-editorial\tools\distill_lessons.py:83-89
  `_meeting_material`（`tools/distill_lessons.py:83-89`）中 `json.loads(d.get("topics") or "[]")` 与 attendees 解析无 try/except，weekly_meetings 表若出现非 JSON 文本（历史脏数据或手工编辑）会直接 ValueError 崩溃，蒸馏任务中断且无降级。建议复用其他函数对 report 解析的 try/except 模式。
