范围：prompts/（agents+knowledge 共 17 个 md）与六个工具，依赖契约对照 novel_editorial/{db,config,llm_client}.py 与 services/{knowledge,audit,activity}.py 验证。基线：python -m compileall 六个工具全部通过；定向测试 tests/test_ai_taste_check.py、test_distill_lessons.py、test_knowledge_keeper.py、test_novel_knowledge.py、test_clean_knowledge.py 共 34/34 通过；CLI 验证 knowledge_keeper --dry-run、export_agent_prompts、sync_from_chapters 幂等复现均符合预期。0158 审查报告的 P1（sync_from_chapters 版本/历史churn）与多项 P3（LIKE 转义、--dry-run 死旗标、备份文件名、docstring）已在 round10 修复并复现确认；遗留的 demo.db knowledge_id=11 重复 history 行是修复前的历史数据。本次仅剩 1 个 P2（export 工具假绿灯）和 5 个 P3（检测启发式与 LLM 输出校验类），均非阻断性，现有代码与测试不会因此破坏。

Full review comments:

- [P2] export_agent_prompts.py 在 proxy 模式下永不导出却返回成功 — E:\code\novel-editorial\tools\export_agent_prompts.py:63-68
  运行 `python tools/export_agent_prompts.py` 只打印一行 PROXY_MODE 说明并以退出码 0 结束，不导出任何文件，而 docstring 承诺 "Export LLM agent system prompts from the n8n workflow into prompts/agents/"。由于 n8n/novel_workflow.json 中 15 个 agent 节点的 jsonBody 全部含 `{agent:'` 且 tools/render_workflow.py:23 硬编码 `PROXY_MODE = True`，第 63-68 行的 `if proxy:` 分支必然触发，第 69 行起的整个导出逻辑不可达。这是一个典型的假绿灯：维护者会误以为 prompts/agents/*.md 由工作流导出（实际方向相反，md 才是真源）。建议删除该工具，或在 proxy 模式下打印明确错误并 `sys.exit(1)`。

- [P3] ai_taste_check 四字排比启发式对普通叙述误报、对真实排比漏报 — E:\code\novel-editorial\tools\ai_taste_check.py:94-107
  tools/ai_taste_check.py:94-107 的启发式用 `re.finditer(r"[\u4e00-\u9fff]{4}", text)` 统计连续 4 字块，测量的是连续汉字串长度而非排比结构。已复现：普通叙述"她站在窗前看了很久，心里想着明天该如何开口解释这件事。"报"疑似四字排比堆砌 2 处"（score 12），而真实排比"天崩地裂，日月无光，山河变色。"因 runs=1 不报任何提示。该工具经 novel_editorial/services/misc.py:ai_taste 暴露给 web API 作为 AI 味检测报告，误报会误导编辑/审稿决策。

- [P3] distill_lessons 收到空 lessons 列表时静默返回成功 — E:\code\novel-editorial\tools\distill_lessons.py:265-270
  tools/distill_lessons.py:196-202 只对非 JSON、非 dict、缺 lessons key、lessons 非 list 报错；模型返回 `{"lessons": []}` 时第 265-270 行返回 `{"ok": true, "drafted": 0, "total_lessons": 0}`。已通过 mock chat_deepseek 复现。调用方 novel_editorial/web_api.py:984 的 distill action 和 services/control.py 每周链只检查 ok/退出码，因此模型输出被截断成合法空数组或键名拼写错误（如 `{"lesson": [...]}`）时，蒸馏静默跳过且无任何失败信号（activity 仅记录 drafted=0）。建议空列表时返回 ok=False 或显式 warning。

- [P3] ai_taste_check 漏检常见写法"不是……而是"（双省略号） — E:\code\novel-editorial\tools\ai_taste_check.py:30-30
  tools/ai_taste_check.py:30 的 FILLER 只收录"不是…而是"（单个 U+2026），而正文中更常见的"不是……而是"（双省略号）不是它的子串。已复现：`detect("他不是……而是直接走开了。")` 的 filler 命中为 0，单省略号形式则命中 1。这使 anti-ai-style.md 与编辑/审稿提示词明确点名的翻译腔检查对常见写法失效，建议把双省略号形式也加入列表（或改用正则）。

- [P3] novel_knowledge.get() 的 entity 参数未转义 LIKE 通配符 — E:\code\novel-editorial\tools\novel_knowledge.py:251-253
  tools/novel_knowledge.py:251-253 中 `get()` 直接拼接 `f"%{entity}%"` 且未加 ESCAPE，与 resolve() 已修复的 `_like_escape`（第 383 行）不一致。已复现：`get(conn, nid, 'plot', '%')` 返回该小说 plot 分类全部行。当前 web_api.py:518/999 的调用不传 entity 参数，无实际触发路径，但 entity 是 API 层可传入参数，属防御性缺口；建议复用 `_like_escape` 保持两处行为一致。

- [P3] knowledge_keeper 未校验 LLM 输出的 JSON schema — E:\code\novel-editorial\tools\knowledge_keeper.py:196-202
  tools/knowledge_keeper.py:196-202 仅对非 JSON 报错；若模型返回合法 JSON 但缺 auto_updates/draft_suggestions/deprecations 任一 key 或字段类型错误（如 `{"foo": 1}`），第 207/220 行的 `parsed.get(...) or []` 全部落空，返回 `{"ok": true}` 且各项为 0。与 distill_lessons 已加的缺失 key 校验不一致。audit 的 keeper_run 记录可观测（invalid 计数），但调用方只看 ok 字段，格式错误的模型输出会被当作正常维护完成。建议对三个 key 做存在性与类型校验。
