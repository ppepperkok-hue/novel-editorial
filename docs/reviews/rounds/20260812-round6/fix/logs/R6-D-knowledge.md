三处都修好了mashitawa，就动了 `tools/novel_knowledge.py` 一个文件，diff 干净，15 增 4 删desuwa。

R6-D-01，`sync_latest` 的无章节分支现在补上了 `skipped` 键：完全空库时在 596 行直接返回空列表，有小说但没章节时走 598-603 行，把 `sync_from_bible` 的结果展开后再显式盖上 `skipped: []`。两条路径都有这个键了desuwa。

R6-D-02，`world_events` 在解析后加了与 `character_states` 完全对称的类型守卫，416 行起：不是 list 就记一条 `{chapter_id, field, reason}` 进 `skipped`，再置空继续处理，不再静默丢desuwa。

R6-D-03，`_add_conflict_draft` 的查重从 `title=?` 改成 `title IN (?, ?)`，117-118 行同时匹配新格式带 `[小说N]` 前缀和旧格式无前缀的标题，升级前的旧草稿也能拦住重复插入desuwa。

验证都过了：`python -m compileall tools/novel_knowledge.py` 编译通过；`pytest tests/test_novel_knowledge.py tests/test_knowledge_bible.py` 14 个测试全绿；另外我内联跑了一轮行为验证，空库、无章节、`world_events` 是 dict、旧格式草稿去重、新格式草稿去重五条路径全部符合预期mashitawa。

测试建议留在报告里，没动测试文件：给 `test_sync_latest_no_data` 加 `skipped == []` 断言，再补一个空库分支的断言；`sync_from_chapters` 补一条 `world_events` 为 dict 时留痕且不产 plot 的用例；`_add_conflict_draft` 补一条预置无前缀草稿后重复调用返回 None 且仍只有一条的用例desuwa。

顺带看到几个额外问题，只报告不改：无章节路径透传 `sync_from_bible` 的 `count` 键，有章节路径没有，两边结构其实还差一个键，这次按任务范围只对齐了 `skipped`；`_add_conflict_draft` 的 `category` 参数从头到尾没用上；还有 `world_events` 元素级非 dict 依旧静默 `continue`，留痕粒度只到字段级，不过和 `character_states` 的取值级行为是对称的，我认为可以接受desuwa。
