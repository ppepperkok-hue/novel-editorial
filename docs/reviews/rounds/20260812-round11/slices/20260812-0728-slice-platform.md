验证基线全部通过（compileall + 68 个相关测试），核心链路（publish_stock 三段发布与完结逻辑、record_work 幂等归档、preflight 锁与手动请求、delete_book FK 安全清理、create_book 主流程）在正常数据形状下行为正确，无 P0/P1 阻断问题。发现 1 个 P2（create_book 对字符串形状 protagonists 崩溃，已复现）和 4 个 P3 非阻断缺陷，均不影响现有测试与默认数据路径，但建议在下一轮修复。

Full review comments:

- [P2] create_book 对字符串形状 protagonists 抛未捕获 AttributeError — E:\code\novel-editorial\tools\create_book.py:271-272
  tools/create_book.py:271-272 中 `_clean_protagonist_name(p.get("name"))` 假定 `protagonists` 是对象数组；当 `novels.protagonists` 存为字符串数组（如 `["林晚","萧然"]`，record_work.upsert_novel 直接 `json.dumps(payload.get("protagonists") or [])` 透传 LLM/面板输入，完全可能产生该形状）时，`'str' object has no attribute 'get'` 抛出且不在 except 捕获列表（仅 URLError/HTTPError/RuntimeError/ValueError）内，CLI 直接 traceback 崩溃而非返回 `{"ok": false}`。已复现：mock `_get_categories` 后调用 `create_book_on_fanqie(conn, 1)` 得到 `AttributeError: 'str' object has no attribute 'get'`。test_create_book.py 全部使用 dict 形状，未覆盖此输入。建议与 get_meta/record_work 的脏数据防御一致，先校验元素类型（字符串元素可包成 `{"name": p}` 或跳过），并把 AttributeError 纳入捕获。

- [P3] preflight CLI 的 already_ran 为全局检查，与 per-book 声明不一致 — E:\code\novel-editorial\tools\preflight.py:227-227
  tools/preflight.py:87-91 的 docstring 声明按书过滤以避免多书互阻，但 main() 第 227 行调用 `check_already_ran(conn)` 不传 novel_id（SQL 无 novel_id 条件），实际是库级检查。当库中并存多本 publishing/finishing 的书（例如 finishing 旧书未耗尽余量时又绑定了新书），旧书今日发布过会导致新书 preflight 报“今日已发布过章节，跳过防重复”而误阻塞。现役调度器 editorial_daily.py:537 用的是 per-book 调用（`check_already_ran(conn, ctx.novel_id)`），故该问题只影响 preflight CLI 路径；main() 应解析活跃书 id 传入。

- [P3] publish_stock db.connect 失败时运行锁残留且异常裸奔 — E:\code\novel-editorial\tools\publish_stock.py:379-388
  tools/publish_stock.py 中 acquire_lock(379) 先于 db.connect(388)，而 connect 不在 try/finally 内：当 `--db` 指向不可打开路径时（已复现：传入目录名 `bad.db` 得到 `OperationalError: unable to open database file`），锁文件 `n8n_tmp/<stem>.lock` 残留，同时异常以 traceback 呈现、无 JSON 错误输出。残留锁通常能靠 PID 死亡自愈，但在进程存活窗口或 PID 被复用时，后续运行会被“运行锁占用”拒绝。建议把 db.connect 移入 try 或用 `conn = None` 初始化并在 finally 中判空。

- [P3] record_work 章节 status 缺失时默认 published，产生虚假成功发布记录 — E:\code\novel-editorial\tools\record_work.py:356-356
  tools/record_work.py:356 `status = str(ch.get("status") or "published")`：当外部 payload 的章节缺少 status 或为空时，本地章节被记为 published 并插入 success 的 publish_logs（第 428-435 行），进而污染存稿池统计与 preflight 的“今日已发布”判断。现役调度器 editorial_steps.build_payload 总是显式写 status，因此主要影响外部/n8n 回传或手写 payload 路径；与文件内其他脏数据防御（_safe_json/_to_int 回退默认值）相比，默认值选“published”过于激进，保守起见应默认 draft/reviewed。

- [P3] collect_reader_stats 仅拉取第一页 200 章，超长书无翻页 — E:\code\novel-editorial\tools\collect_reader_stats.py:69-69
  tools/collect_reader_stats.py:69 固定 `page_index=0, page_count=200` 且无翻页循环；书超过 200 章后，第 201 章及以后的章节不会出现在 chapter_stats_list，也就不会写入 reader_stats.csv，data_feedback 的完读率/追读率统计与低质章节标记会静默缺失这些章节。fanqie_item_id 与本地 seq 的映射基于全表，所以缺口只来自 API 分页上限；对超长连载书需循环翻页或用更大的 page_count。
