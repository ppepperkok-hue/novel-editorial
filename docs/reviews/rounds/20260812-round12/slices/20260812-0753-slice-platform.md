审查范围内无 P0/P1 阻断性问题：语法基线通过，SQL 占位符、锁协议（preflight.acquire_lock/release_lock 与 publish_stock/editorial_daily/release_lock 的一致性）、SQLite FK 清理顺序（delete_book._purge_novel 覆盖全部引用表）经核对正确。发现的 8 项均为条件性触发（同名书合并、alerts.log 不可写、网络超时、PID 复用等），不阻塞现有代码与测试的正常运行，但 record_work 同名合并与两处未保护日志写入建议尽快修复。

Full review comments:

- [P2] upsert_novel merges a new book into an older same-title novel — E:\code\novel-editorial\tools\record_work.py:68-71
  tools/record_work.py:71 的 title 回退匹配 `SELECT id, outline FROM novels WHERE title=?` 没有 ORDER BY/LIMIT，novels.title 也无 UNIQUE 约束。实测复现：库中先有同名旧书（finished）再插入同名新书后，`record_payload` 返回旧书 novel_id=1，旧书的 premise/tags/abstract/outline 及后续章节、角色、成本全部写入旧书（UPDATE 不更新 status，旧书保持 finished 但数据被覆盖）。触发条件是 payload 的 book_id 为空或与库不匹配（未绑定活跃书、重放 n8n 遗留 payload 时），此时存在同名旧书即污染。修复应加 `ORDER BY id DESC LIMIT 1` 并对已完结/非活跃书跳过 title 匹配；tests/test_record_work.py 无同名场景覆盖。

- [P2] publish_batch alerts.log writes lack OSError protection — E:\code\novel-editorial\tools\publish_stock.py:298-303
  tools/publish_stock.py:298-303 与 326-331 两处 `alerts.open("a", ...)` 直接写入，无 try/except。项目内其余日志写入（record_work._trace、create_book._warn、本文件 _safe_int_setting、audit.log）全部有 OSError 兜底，实测 alerts.log 不可写时同类调用抛 PermissionError。此处一旦失败：发布循环中断（已发布章节已 commit，剩余章节不发布）、CLI 无 JSON 输出、editorial_daily 的 publish_batch 调用抛异常。

- [P2] preflight.alert is unprotected while sibling helpers swallow OSError — E:\code\novel-editorial\tools\preflight.py:54-56
  tools/preflight.py:54-56 `alert()` 无异常保护，实测将 alerts.log 指向目录时抛 PermissionError。cookie 失效或预算超限路径会调用 alert()，此时 alerts.log 不可写（权限/磁盘/占用）会使整个 preflight.main 崩溃、无 JSON 输出，n8n/scheduler 无法分支；同项目 _trace/_warn 均用 try/except OSError 兜底，此处应一致。

- [P3] create_book has no idempotency after network errors — E:\code\novel-editorial\tools\create_book.py:342-344
  tools/create_book.py:342-344 中 http_json 超时（urlopen timeout=30）或响应解析失败时返回"建书请求失败"，但请求可能已到达番茄并建书成功；重试会触发平台"每天最多 1 本"限制，且该错误路径不返回 book_id，用户无法直接手动绑定已建的书。建议超时/解析失败时提示可能已建书并保留现场供人工核对。

- [P3] n8n_api.py crashes with IndexError when run without arguments — E:\code\novel-editorial\tools\n8n_api.py:96-97
  tools/n8n_api.py:97 `action = sys.argv[1]` 无参数保护，`python tools/n8n_api.py` 直接 IndexError traceback；同文件 run action 对缺失 wf_id 有显式提示（135-137 行），此处风格不一致，应打印用法后 exit(1)。

- [P3] .env parsing in inject_fanqie_cookie.py / start_n8n.ps1 diverges from config.load_env — E:\code\novel-editorial\scripts\inject_fanqie_cookie.py:17-21
  scripts/inject_fanqie_cookie.py:18-20 与 scripts/start_n8n.ps1:14-18 按 `key=value` 原样取值，不剥离行尾 ` # comment`；novel_editorial/config.py:85-96 的 _strip_inline_comment 专门处理了该格式。若 ~/.n8n/.env 含 `KEY=value # comment`，注入的 cookie 与 n8n 进程环境变量会带注释后缀，与 publish 链（config.load_env）读到的值不一致，导致 cookie 失效。建议复用 config 的解析逻辑。

- [P3] acquire_lock can wedge forever on PID reuse (no age fallback) — E:\code\novel-editorial\tools\preflight.py:153-156
  tools/preflight.py:153-156 中 PID 可解析时 `stale = not _pid_alive(pid)`，完全绕过 2 小时年龄规则。Windows 下 PID 被系统复用给无关进程时 _pid_alive 返回 True，锁永不回收，日更每天 acquire_lock 失败直到人工删除 n8n_tmp/*.lock。建议对"PID 存活但锁龄超阈值（如 24h）"也允许回收。

- [P3] check_stock counts whole-library stock when no active book — E:\code\novel-editorial\tools\check_stock.py:37-43
  tools/check_stock.py:37-43 在 novel_id=0 且无 publishing/finishing 活跃书时，stock_sql 无 novel 过滤，返回全库（含 planning 书）的 reviewed 计数，scope 标记为 "none" 但 stock/target/need 数值仍会输出并被 n8n 旧工作流消费。CLI 场景（无 --novel-id 且无活跃书）会得到误导性库存。建议 scope=none 时显式返回 stock=0 或错误提示。
