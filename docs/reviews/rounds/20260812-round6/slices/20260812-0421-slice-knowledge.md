审查范围：prompts/、tools/novel_knowledge.py、tools/knowledge_keeper.py、tools/distill_lessons.py、tools/clean_novel_knowledge.py、tools/ai_taste_check.py、tools/export_agent_prompts.py（含 e35d379 提交改动），依赖接口（db.py/config.py/llm_client.py/services/*）仅做契约核对。基线：python -m compileall 全过；定向测试 test_novel_knowledge/test_clean_knowledge/test_knowledge_keeper/test_distill_lessons/test_ai_taste_check/test_knowledge_bible 共 29 个全绿；CLI 级实测验证了 --dry-run/--apply 语义、备份命名、sync-latest 输出、character_states 非 dict 跳过留痕、冲突草稿跨书隔离均符合预期。未发现 P0/P1/P2 问题：usage 空值守卫、attendees/kind 从库读取、DISTINCT 排序修复、SQL 参数化、UTF-8 编码均正确；3 个 P3 发现均为本次提交引入的结构不对称/防御不完整/旧数据兼容问题，不阻塞合并。

Full review comments:

- [P3] sync_latest 两条路径返回结构不一致，无章节分支缺少 skipped 键 — E:\code\novel-editorial\tools\novel_knowledge.py:601-608
  本次改动给有章节路径新增了 `skipped` 键（tools/novel_knowledge.py:601-608），但无章节分支（587-593 行）仍返回 `sync_from_bible` 展开的 `{ok, novel_id, updated, count}`，不含 `skipped`。两条路径的返回 schema 不对称：任何按统一结构消费 `sync_latest` 结果的调用方（CLI 解析、日志统计）在无章节库上会缺键。当前调用方（editorial_daily._run_tool、CLI 打印）仅透传不解析，故不产生实际崩溃，但属于本次提交引入的契约不一致，建议在无章节分支补上 `skipped: []` 使结构对齐。

- [P3] world_events 缺类型守卫，LLM 输出 dict 时事件被静默丢弃且无留痕 — E:\code\novel-editorial\tools\novel_knowledge.py:412-415
  本次为 `character_states` 增加了 isinstance(dict) 守卫并写入 `skipped`（tools/novel_knowledge.py:403-411），但紧随其后的 `world_events` 解析（412-415 行）没有对称校验：若 LLM 把 world_events 写成 JSON 对象而非数组，`for ev in events` 会迭代键名字符串，全部被 `isinstance(ev, dict)` 过滤，事件数据静默丢失且不进 `skipped`。与 character_states 的防御不对称，修复意图（非预期类型不中断整批、留痕可查）对 world_events 未生效。建议对 events 同样做 isinstance(list) 校验并记入 skipped。

- [P3] 冲突草稿 title 前缀使升级前旧数据无法命中新去重查询，可能重复建草稿 — E:\code\novel-editorial\tools\novel_knowledge.py:114-119
  `_add_conflict_draft` 的去重键改为带 `[小说N]` 前缀的 title（tools/novel_knowledge.py:114-119），但库中已存在的旧 auto_conflict 草稿（title 无前缀）不会被新查询命中；升级后同一实体再次冲突时会插入第二条草稿。一次性数据问题（人工可清，不影响正确性），但若希望平滑迁移，可在首次运行时对旧 title 做一次前缀补写或查询时兼容两种形式。
