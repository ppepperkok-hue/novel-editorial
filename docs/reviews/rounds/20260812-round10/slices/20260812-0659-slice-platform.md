审查范围：scripts/、tools 平台切片（publish_stock/create_book/check_stock/get_meta/record_work/delete_book/collect_reader_stats/current_book/preflight/release_lock/n8n_api）、pyproject.toml、launch_desktop.vbs。基线：切片文件 compileall 全部通过；check_stock、current_book、release_lock、preflight、get_meta、record_work（含 run_id 幂等重跑）、delete_book（FK 安全清理）均在真实 demo.db 上冒烟通过，未发现 P0/P1 阻断性问题；cost_logs 幂等、_purge_novel 无孤儿行均已验证。发现 3 个 P2（pending_publish 部分发布后静默清零、check_stock 全库统计与活跃书发布范围不一致导致 n8n 链路少生成、读者统计缺失率按 0.0 计入误导低质反馈）和 3 个 P3，均不阻断现有功能，建议下一轮修复。

Full review comments:

- [P2] publish_stock 部分发布成功后仍清零 pending_publish，剩余章节静默丢失 — E:\code\novel-editorial\tools\publish_stock.py:427-433
  tools/publish_stock.py:427-433 中 `target = max(0, min(target, 10))` 把单次发布上限硬编码为 10，随后 `if settings.get("pending_publish") and summary.get("published")` 无条件把 pending_publish 置 0。复现：pending_publish=12 时 target=10，只发布 10 章后 pending 被清零，剩余 2 章永远不再发布；pending_publish=5 且其中 2 章失败（published=3）时 pending 同样被清空，失败章节不再重试。模拟验证输出 `pending=12 target=10 reset_pending=True -> remaining pending after reset: 2`。修复方向：仅在 `published >= 请求数` 时清零，或按 `pending - published` 回写剩余值。

- [P2] check_stock 默认按全库统计存稿，与 publish_stock 的活跃书范围不一致 — E:\code\novel-editorial\tools\check_stock.py:25-30
  tools/check_stock.py:25-30 在未传 `--novel-id` 时统计**所有**小说的 reviewed 章节数，而 tools/publish_stock.py:238-245 只发布活跃书（publishing/finishing 的最新一本）的存稿；n8n 调用点 n8n/novel_workflow.json:1891 正是 `check_stock.py --db demo.db`（不带 --novel-id）。一本完结书在收尾批次后留下的 reviewed 章节永远不会被发布，却持续计入 stock。复现：完结书留 1 章 reviewed + 新活跃书 0 存稿时，check_stock 报 `{"stock": 1, "target": 2, "need": 1}`，而按活跃书实际应为 need=2（新调度器 tools/editorial_daily.py:1744 已按 ctx.novel_id 限定，n8n 旧链路未修）。后果是 n8n 流程对活跃书少生成或完全不生成章节，静默停摆。

- [P2] collect_reader_stats 把缺失的完读/追读率写成 0.0，误导低质章节反馈 — E:\code\novel-editorial\tools\collect_reader_stats.py:135-144
  tools/collect_reader_stats.py:142-143 中 `finish_rate: finish if finish is not None else 0.0`：当 API 对某章返回空/缺字段时（例如刚发布尚无读者数据），norm_rate 返回 None，但行内被替换成 0.0 而非跳过。下游 novel_editorial/data_feedback.py `low_performers` 阈值 0.20 会把这章标记为低质（模拟输出 `low_chapters: [5]`），并通过 get_meta 的 reader_feedback 注入给 LLM，可能触发对正常章节的不必要重写，同时拉低 avg_finish。建议缺失字段时跳过该行或单独标记，而不是按最差 0% 处理。

- [P3] get_meta 读取非对象结构的 hot_topics.json 时 AttributeError 崩溃 — E:\code\novel-editorial\tools\get_meta.py:74-86
  tools/get_meta.py:74-86 只捕获 `(OSError, ValueError)`，但 `hot_data = json.loads(...)` 后立即调用 `hot_data.get("sources")`；若文件是合法 JSON 数组（如 `["a","b"]`），会抛 `AttributeError: 'list' object has no attribute 'get'` 使整个 CLI 崩溃。已复现（exit 崩溃，stderr 见 AttributeError）。文件由流水线写入，正常是 dict，但损坏/被误写时该工具没有像其他字段那样降级到 alerts.log，与文件内其余防御式处理不一致。建议对非 dict 结构同样回退空对象。

- [P3] release_lock 不校验锁归属，可误删并发运行持有的锁 — E:\code\novel-editorial\tools\release_lock.py:17-22
  tools/release_lock.py:17-22 与 tools/preflight.py:199-206 的 release_lock 都是无条件 unlink 锁文件，而 acquire_lock 写入 PID 并在 _pid_alive 中校验存活进程；释放侧从未比对 PID。并发场景：手动运行与定时运行重叠时，先结束的一方会把另一方仍在持有的 `n8n_tmp/demo.lock` 删掉，使第三个运行能通过 acquire_lock 造成重复发布。概率低（日常流程基本串行），但锁语义不对称，建议释放时校验文件内 PID 是否为当前进程。

- [P3] _run_fix_worker.ps1 未转义任务文本中的双引号，可破坏 node 命令行 — E:\code\novel-editorial\scripts\_run_fix_worker.ps1:34-50
  scripts/_run_fix_worker.ps1:48 把任务 markdown 原样拼进 `'"' + $taskText + '"'` 作为 node 参数，仅替换了换行；任务文本若包含 `"`（markdown 引用、代码块等很常见），拼出的命令行会被截断/错位，Start-Process 传给 node 的参数解析错误，可能执行错误 prompt 或直接失败。run_review.ps1 同样用此方式拼 persona 文本。建议对 `"` 转义或改用 stdin 传入（与 -DryRun 提示的 `codex exec --ephemeral -` 一致）。
