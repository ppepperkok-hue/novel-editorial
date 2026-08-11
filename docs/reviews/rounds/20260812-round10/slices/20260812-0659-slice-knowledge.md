切片内 6 个工具的语法编译通过，46 个定向测试全绿，但存在两个可复现的真实缺陷：graph() 对非对象 outline/bible 直接 500（API 可达），upsert_ex 基于 120 字符截断内容做合并判定导致长内容被静默并入错误实体并覆盖；另有 keeper 热点 sources 内部结构未守卫的健壮性缺口。

Full review comments:

- Guard graph() against non-object outline/bible JSON — E:\code\novel-editorial\tools\novel_knowledge.py:329-334
  tools/novel_knowledge.py:331-334 `graph()` 仍用裸 `json.loads(novel["outline"] or "{}")...get("bible")` 解析设定，未套用 round8 为 `sync_latest` 新增的 `_outline_bible` 类型守卫。实测：outline 为合法 JSON 数组（如 `[1,2]`）或 `bible` 为数组时，`bible.get("relationships")` 抛 `AttributeError: 'list' object has no attribute 'get'`，GET /api/novel_knowledge/graph（web_api.py:503）直接 500；而同一种脏数据在 `sync_latest` 中只会产生 warnings 并优雅回退，说明该输入类型是已知会出现的。当前没有任何测试覆盖 graph() 的畸形 outline 分支。建议复用 `_outline_bible` 的 isinstance 校验后再取 `relationships`。

- Compare merge similarity against full stored content, not 120-char head — E:\code\novel-editorial\tools\novel_knowledge.py:99-99
  tools/novel_knowledge.py:99 `find_similar` 把候选行的 content 截断到 120 字符，而 :195 `upsert_ex` 用这个截断串与新内容算 `_similarity` 来决定是否自动合并。实测：现有行内容 129 字符、新实体内容前 120 字符相同但结尾完全不同（`...完全不同的结尾内容`），`upsert_ex(check_similar=True)` 仍判定 `merged_into=阴阳守恒` 并把新内容覆盖进旧行（旧值仅留在 history）。该路径经 POST /api/novel_knowledge {action:"upsert"} 触发（web_api.py:1005 恒传 check_similar=True），导致用户新增的独立条目被静默并入错误实体且内容被替换。合并判定应使用完整存储内容（截断只应作用于展示字段）。

- Guard hot topics sources inner structure in knowledge_keeper input — E:\code\novel-editorial\tools\knowledge_keeper.py:113-123
  tools/knowledge_keeper.py:113-123 `_input_payload` 对 `hot.get("sources")` 直接迭代并对每个元素调用 `s.get(...)`；round9 的守卫（:92）只校验了顶层是 dict，若 sources 是 dict/字符串（hot_topics.json 位于仓库根目录、可手工编辑，round9 正是为此加了顶层守卫与审计告警），`run()` 会抛 AttributeError 且整个知识管家运行失败、不留任何 audit/activity 记录。建议对 sources 增加 isinstance(list) 校验，与顶层守卫走同一 warning 回退路径。
