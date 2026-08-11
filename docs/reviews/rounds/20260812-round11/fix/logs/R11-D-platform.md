修完了mashitawa。七个修复项全部落地，编译、相关测试、全量测试和逐项行为断言都过了，细节在下面。

| 项 | 文件:行号 | 改动摘要 | 验证 |
|---|---|---|---|
| R11-D-01 | [create_book.py](/E:/code/novel-editorial/tools/create_book.py:113) | 新增 `_warn` 与 `_normalize_protagonists`（122-162 行）；protagonists 支持 list（dict/字符串元素）、dict（单条或 name→描述映射）、纯字符串清洗，非法形状回退空列表；清洗/回退/跳过均写 alerts.log | 7 种形状断言 + 留痕断言全过；test_create_book 全绿 |
| R11-D-02 | [preflight.py](/E:/code/novel-editorial/tools/preflight.py:228) | main() 先取 publishing/finishing 最新一本，按书维度调 `check_already_ran`；无活跃书时 already_ran 置 False；输出与 audit detail 增加 `already_ran_novel_id`，docstring 同步为 per-book 语义 | 双书场景验证：只查活跃书（id=2），全局有发布也不误拦；test_preflight_guard/test_book_isolation/test_editorial_daily/test_workday 全绿 |
| R11-D-03 | [publish_stock.py](/E:/code/novel-editorial/tools/publish_stock.py:389) | `db.connect` 包 try/except，失败时先 `release_lock` 再输出 `{"ok": false, "error": "数据库连接失败：…"}` 返回，异常不再裸奔 | mock 连接抛错验证：锁释放被调用、JSON 错误明确；test_publish_stock 全绿 |
| R11-D-04 | [record_work.py](/E:/code/novel-editorial/tools/record_work.py:370) | status 缺失/空白不再默认 published，显式标记 `unknown` 并留痕，不插入成功 publish_logs | 行为验证：章节落库 unknown、success 日志数为 0；test_record_work 全绿 |
| R11-D-05 | [record_work.py](/E:/code/novel-editorial/tools/record_work.py:107) | upsert_characters 对非 dict 元素跳过+留痕；record_payload 活动统计对非 dict chapter 安全取值+留痕（540-556 行） | 行为验证：非 dict 角色/章节不崩，统计 published=1/failed=1/chapters=3 正确；test_record_work 全绿 |
| R11-D-06 | [collect_reader_stats.py](/E:/code/novel-editorial/tools/collect_reader_stats.py:74) | fetch_stats 翻页循环：每页 200，短页即末页，上限 100 页并留痕；中途页失败报错，不写部分数据 | 行为验证：两页合并 250 条、page_index 0→1、上限留痕均通过；test_services_regression 全绿 |
| R11-D-07 | [get_meta.py](/E:/code/novel-editorial/tools/get_meta.py:97) | sources 非 list 回退+留痕、元素非 dict 跳过+留痕、titles 非 list 跳过；top_keywords 非 list 回退+留痕（116-119 行） | 行为验证：dict sources/字符串 top_keywords 不崩、输出回退为空、alerts 留痕；get_meta 冒烟输出正常 |

验证汇总：`python -m compileall` 六个文件通过；8 个直接相关测试文件 93 passed；全量 `python -m pytest` 497 passed；额外 22/22 行为断言通过。diff 只落在指派六个文件，其他并行改动（meeting_session.py、web_api.py）和未跟踪审查产物都没碰，也没有 git add/commit。

测试建议（测试文件不在指派范围，我没改）：test_create_book 补 protagonists 字符串/纯名字/非法形状归一化用例；test_preflight_guard 补双书与无活跃书时 `already_ran_novel_id` 断言；test_publish_stock 补连接失败锁释放用例；test_record_work 补缺失 status 与顶层非 list 形状用例；collect_reader_stats 与 get_meta 分别补翻页合并/上限留痕、dict sources 回退用例。

额外问题，只报告不改：record_payload/upsert_novel 的 chapters、protagonists、tags 顶层形状仍未强制 list，字符串会被逐字符迭代跳过或原样序列化写库，统计口径可能失真；collect_reader_stats 的翻页依赖“短页即末页”启发式，接口没有 total 字段依据，若单页上限实际低于 200 仍有截断风险，页数上限留痕只是兜底；get_meta 的 bible/blueprints 错位形状不会崩但会原样进输出，是第六轮就报过的残余边界。MEMORY.md 不在允许修改范围，没有更新；记忆库那边我已记了一笔本轮进展desuwa。
