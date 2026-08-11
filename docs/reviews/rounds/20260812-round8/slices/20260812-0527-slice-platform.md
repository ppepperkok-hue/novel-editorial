语法基线（python -m compileall 全部指定文件）通过，但存在已复现的缺陷：get_meta 对脏 bible 崩溃且被调度器静默当作空上下文（P1），record_work 对非 int 字段崩溃导致归档失败及同 run_id 重复归档产生重复伏笔/演化数据（P2）。这些会在 LLM 输出脏数据或运行重试时实际触发并破坏连载上下文一致性与数据完整性，建议修复后再合入。

Full review comments:

- [P1] get_meta 对 bible.characters 非 dict 元素崩溃，日更上下文静默丢失 — E:/code/novel-editorial/tools/get_meta.py:133-136
  tools/get_meta.py:134 中 `for c in bible.get("characters") or []` 直接调用 `c.get("name")`，当 outline.bible.characters 含字符串元素（LLM 生成的脏 bible，如 `["张三","李四"]`）时抛 AttributeError。已复现：构造该 outline 后运行 `python tools/get_meta.py B1 --db <tmp>`，returncode=1，stderr 为 `AttributeError: 'str' object has no attribute 'get'`。调用方 tools/editorial_daily.py:_get_meta 不检查 subprocess returncode，stdout 为空时解析为 `{}`，`build_writing_context({})` 把上一章结尾、角色状态、活跃伏笔、已有标题（防重复）、圣经全部当作空——日更静默降级为“第 1 章”场景，可能导致章节设定漂移与标题重复，且无任何告警。建议与文件内 `_safe_json` 等防御风格一致，对字符元素做 isinstance 检查。

- [P2] record_work 对非 int words/prompt_tokens 崩溃导致整次归档失败 — E:/code/novel-editorial/tools/record_work.py:306-307
  tools/record_work.py:306 `words = int(ch.get("words") or 0)` 与 :414-415 `int(c.get("prompt_tokens") or 0)` 对非整数字符串（如 `"2,000"`、`"12.5"`）抛 ValueError。已复现：payload 中 `words: "2,000"` 调用 `record_payload` 得到 `ValueError: invalid literal for int() with base 10: '2,000'`，当日 chapters/summaries/costs 全部未写入（调度器经 _run_tool 仅追加 warning，归档静默丢失）。同文件对 expected_recover 已有 try/except 防御先例，此处应同样做防御性转换或跳过脏字段。

- [P2] record_work 同 run_id 重复归档产生重复伏笔/演化/事件行 — E:/code/novel-editorial/tools/record_work.py:235-242
  tools/record_work.py 仅对 cost_logs 做了 run_id 幂等（:415 前 dup 检查），而 _upsert_summary 中 character_evolution（:198）、world_events（:235）、plot_threads（:241/:271）均为无条件 INSERT。已复现：同一 run_id payload 连续调用 record_payload 两次后 cost_logs=1 行，但 character_evolution=2、world_events=2、plot_threads=2（重复 open 伏笔线）；后续 foreshadowing_recovered 关闭时 `ORDER BY planted_chapter LIMIT 1` 只关一条，另一条永久残留 open 并出现在 get_meta 的 plot_threads 中。n8n 重试或调度器重复归档同一结果时数据会持续膨胀。

- [P3] check_stock 默认分支不识别 finishing 状态书，收尾期查存稿返回空 — E:/code/novel-editorial/tools/check_stock.py:48-51
  tools/check_stock.py:50 默认（novel_id=0）查询 `WHERE status='publishing'`，而 current_book.py / publish_stock.py / collect_reader_stats.py 均用 `status IN ('publishing','finishing')`。已复现：临时库中只有 finishing 状态书时，`check_stock(conn, 0)` 返回 `novel_id:0, book_id:'', book_name:''`，而 `current_book(conn)` 正确返回该书——收尾阶段单独运行 `python tools/check_stock.py` 拿不到活跃书元数据。调度器（editorial_daily.py:1729）传 novel_id 不受影响，仅 CLI 手工路径受影响。

- [P3] preflight CLI 在未持有运行锁时消费 manual_run_requested — E:/code/novel-editorial/tools/preflight.py:253-258
  tools/preflight.py:253-258 在 `ok and manual_requested` 时直接把 manual_run_requested 置 0，而 main() 是 check-only 进程、不获取运行锁（:307 注释亦声明）。若预检通过但实际运行（调度器）随后因锁被占用或后续环节失败而跳过，手动请求已被消费且无提示，与注释“Consume the manual-run request only when this run will actually proceed”矛盾。对照 tools/editorial_daily.py:_preflight 是 acquire_lock 成功后才 `set_many(conn, {"manual_run_requested": "0"})`，顺序正确。现役调用者主要是遗留 n8n workflow，风险取决于是否有人手动跑该 CLI。

- [P3] publish_stock CLI 入口不检查运行锁，可绕过防双发保护 — E:/code/novel-editorial/tools/publish_stock.py:357-361
  tools/publish_stock.py main()（:357 起）直接选 reviewed 章节发布，不调用 preflight.acquire_lock，而 tools/preflight.py:22 的锁注释明确目的是防止“concurrent scheduled + manual runs … double-publishing”。定时调度器持有 `n8n_tmp/<db>.lock` 运行时，手动 `python tools/publish_stock.py` 仍可并发把同一批 status='reviewed' 章节重复发布到番茄（两个进程各自 new_article/cover_article/publish_article 并写库）。调度器内部路径（publish_batch 经 _preflight 加锁）安全，缺口仅在 CLI 手动入口。
