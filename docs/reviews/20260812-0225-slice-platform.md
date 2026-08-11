审查范围：scripts/、tools 下 11 个平台工具、pyproject.toml、launch_desktop.vbs，并核对 db.py/config.py/services/* 契约。基线：12/13 个 slice Python 文件 py_compile 通过，scripts/inject_fanqie_cookie.py 编译失败（IndentationError:95）；current_book/check_stock 在真实 demo.db 上运行正常；在 demo.db 副本上复现 _purge_novel 的 FK IntegrityError（按指示未跑全量测试套件）。存在 2 个 P1（注入脚本整体不可运行、删书工具主路径 FK 崩溃且远端已删）、1 个 P2（多书 CLI 选错发布目标）及若干 P3，故判为不正确，需修复后合入。

Full review comments:

- [P1] inject_fanqie_cookie.py 顶层残留缩进块导致 IndentationError，脚本完全无法运行 — E:\code\novel-editorial\scripts\inject_fanqie_cookie.py:94-105
  `scripts/inject_fanqie_cookie.py:95-105` 在 `main()` 结束（92 行 `ws.close()`）之后残留了一段模块级缩进代码（`mid = seq["n"]`、`cmd("Input.dispatchMouseEvent"...)` 等），这是提交 642552d 删除 `click_select` 死代码时只删了 `def click_select(...)` 头与前三行、留下函数体的结果。验证：`python -m py_compile scripts/inject_fanqie_cookie.py` 报 `IndentationError: unexpected indent (line 95)`，整个文件无法编译，Cookie 注入工具完全失效（`git show 642552d -- scripts/inject_fanqie_cookie.py` 可见删除不完整）。修复只需删除 94-105 行的残留块。

- [P1] delete_book._purge_novel 漏删 novel_knowledge_history，FK 违例使清除失败并留下孤儿数据 — E:\code\novel-editorial\tools\delete_book.py:64-78
  `tools/delete_book.py:71-77` 的 `_purge_novel` 按 chapter_id / ref_novel_id / novel_id 列清理子表，但 `novel_knowledge_history` 只通过 `knowledge_id REFERENCES novel_knowledge(id)` 关联（无 novel_id/chapter_id/ref_novel_id 列），不会被清理；随后 novel_id 遍历删除 `novel_knowledge` 时触发 `IntegrityError: FOREIGN KEY constraint failed`。已在 demo.db 副本上复现：novel 1 有 19 条 history 行引用其 knowledge，`_purge_novel(1)` 直接抛异常。由于番茄端书籍已在 purge 之前删除（不可逆），异常未被 `delete_book_on_fanqie` 捕获（try 只包住网络请求），main() 以 traceback 崩溃、本地事务回滚——本地 novel 行保留且 book_id 指向已删除的远端书籍，后续日更发布持续失败。现有 `tests/test_delete_book.py::test_purge_novel_is_fk_safe` 未插入 novel_knowledge/history 行，故该路径无测试覆盖。

- [P2] publish_stock CLI 在多书并存时选中最小 novel_id 而非活跃书 — E:\code\novel-editorial\tools\publish_stock.py:335-341
  `tools/publish_stock.py:335-341` 用 `SELECT DISTINCT novel_id ... ORDER BY novel_id` 取第一个非 finished 小说作为发布目标，而活跃书语义（`tools/current_book.py:21-24` 取最新 publishing/finishing，`docs/evolution.md:430` 记载“publish_stock 多书按活跃书发布”）是最新一本。仅当至少两本未完结小说同时有 reviewed 存稿时，CLI 会把稿子发到最老的那本书上，与工作流/调度器（editorial_daily 用 ctx.novel_id）目标不一致。建议按活跃书（status IN ('publishing','finishing') ORDER BY id DESC）选取，或提供 --novel-id 参数。

- [P3] publish_stock 对 pending_publish/daily_chapters 的 int() 无容错，脏配置直接崩溃 — E:\code\novel-editorial\tools\publish_stock.py:356-358
  `tools/publish_stock.py:356-358` 直接 `int(settings.get("pending_publish") or 0)` / `int(settings.get("daily_chapters") or 2)`，settings 由面板/手工写入，一旦为 "abc" 等非数字即抛 ValueError 使整个发布 CLI 崩溃；同批工具 check_stock 已按 R2-P3-15 加了 try/except 容错，此处未同步，行为不一致。

- [P3] preflight.py --env-file 参数是空操作（load_env 忽略入参） — E:\code\novel-editorial\tools\preflight.py:38-40
  `tools/preflight.py:38-40` 的 `load_env(env_file)` 从不使用 `env_file`，只调 `config.load_env()` 读默认路径；`main()` 206 行 `load_env(args.env_file)` 传入的自定义路径被丢弃，用户传 `--env-file` 期望加载别的环境文件时行为不变，属误导性参数。

- [P3] collect_reader_stats.py --env-file 参数是空操作（load_env 忽略入参） — E:\code\novel-editorial\tools\collect_reader_stats.py:28-30
  `tools/collect_reader_stats.py:28-30` 的 `load_env(env_file)` 同样忽略入参，`run()` 79-80 行与 main() 139 行传入的 `--env-file` 自定义路径不生效，始终加载 `config.load_env()` 的默认 ~/.n8n/.env。

- [P3] get_meta.py 多处 json.loads 无保护，脏 JSON 使 CLI 整体崩溃 — E:\code\novel-editorial\tools\get_meta.py:104-106
  `tools/get_meta.py:104-106`（protagonists/characters.state）与 157-158 行（tags 两处）直接 `json.loads(...)` 且无 try/except；R2-P3-14 只给 outline 加了保护。这些列由 LLM 链路/手工写入，一旦含 `[object Object]` 等脏值，get_meta 抛异常退出，n8n/调度器取元数据链路失败且无降级输出（同文件 hot_topics/reader_stats 读取均有保护，此处不一致）。

- [P3] record_work 对 expected_recover 的 int() 无容错，LLM 脏数据使整次记录崩溃 — E:\code\novel-editorial\tools\record_work.py:230-230
  `tools/record_work.py:230` `int(p.get("expected_recover") or 0)` 未包 try/except；`foreshadowing_planted` 来自 LLM 摘要 JSON，若 expected_recover 为非数字字符串（如“第20章”），ValueError 会让 record_work 整次崩溃、当日成果无法落库（前置的 upsert_novel/upsert_chapters 已 commit，会造成半写入状态）。

- [P3] launch_desktop.vbs 无 BOM UTF-8 中文提示会被 cscript 按 ANSI 解码成乱码 — E:\code\novel-editorial\launch_desktop.vbs:6-7
  `launch_desktop.vbs` 首字节为 `53 65 74 20`（无 BOM），且 7 行 MsgBox 含中文；wscript/cscript 对无 BOM 的 .vbs 按系统 ANSI 代码页解码（中文系统 GBK、英文系统 cp1252），UTF-8 字节会被读成乱码，用户双击后即使弹出“Electron 未安装”提示也无法读懂，错误指引失效。建议将 MsgBox 文案改为 ASCII 或把文件存为 UTF-16/GBK。
