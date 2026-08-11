审查范围：scripts/、tools 下 11 个平台工具、pyproject.toml、launch_desktop.vbs 及依赖接口（db/config/services）。基线：全部目标文件 ast.parse/compileall 通过，6 个 PowerShell 脚本 Parser 语法通过，针对性测试 40 例全绿（test_record_work/test_preflight_guard/test_book_isolation/test_publish_stock/test_delete_book/test_create_book），get_meta/current_book/check_stock/release_lock 用真实 demo.db 运行正常；锁文件命名在 preflight/editorial_daily/autopilot/release_lock 间一致（{stem}.lock），已排除锁不一致误报。未发现 P0/P1 阻塞问题，唯一功能级 bug（rename_on_login.ps1 自杀）属遗留一次性迁移脚本、现役路径不受影响，其余均为 P3 健壮性/死代码/文档问题；现役发布链（publish_stock 本地时间）与 preflight 幂等检查一致。

Full review comments:

- [P2] rename_on_login.ps1 会在重命名前杀死自身进程 — E:/code/novel-editorial/scripts/rename_on_login.ps1:30-33
  scripts/rename_on_login.ps1:30-33 的 `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "novel[-_]pipeline" } | Stop-Process -Id $_.ProcessId -Force` 会匹配到运行本脚本的 powershell 进程自身（其命令行含 `E:\code\novel-pipeline\scripts\rename_on_login.ps1`），在 `Rename-Item`（行 37）之前把脚本自己强杀：catch 块不执行、RunOnce 不会 Rearm，系统随后清理 RunOnce 键，重命名静默失败且不再重试。已用正则模拟验证命令行匹配成立（`MATCH -> current process would be Stop-Process'd`）。该 bug 仅在目录仍为 novel-pipeline 的遗留迁移场景触发，现役目录已改名故不阻塞当前使用。

- [P3] n8n_api.py 登录响应无 Set-Cookie 时抛 TypeError 而非 RuntimeError — E:/code/novel-editorial/tools/n8n_api.py:23-23
  tools/n8n_api.py:23 `for h in r.headers.get_all("Set-Cookie")`：http.client 的 HTTPMessage.get_all 在 header 缺失时返回 None（已用实验验证：`TypeError: 'NoneType' object is not iterable`），因此登录失败或返回异常响应（无 n8n-auth cookie）时抛出的是 TypeError 而非预期的 RuntimeError("no n8n-auth cookie")，掩盖真实登录错误。仅在登录失败路径触发，影响错误可诊断性。

- [P3] preflight.py 的 --no-lock 参数定义后从未被读取 — E:/code/novel-editorial/tools/preflight.py:199-203
  tools/preflight.py:200 定义了 `--no-lock`（帮助文本声称 check-only 模式不持有日更锁），但 main() 中从未引用 args.no_lock（rg 全文件无命中），该参数对行为零影响，CLI 用户按帮助调用会得到与预期不符的结果，属误导性死参数。

- [P3] publish_stock.py 存在不可达的 finished 死分支 — E:/code/novel-editorial/tools/publish_stock.py:352-354
  tools/publish_stock.py:352 `if novel and novel["status"] == "finished"` 不可达：novel 只能来自 343 行循环且该循环已过滤 `cand["status"] != "finished"`，而 novel is None 时 345-350 行已提前 return。该分支连同其错误输出永远不会执行，属死代码。

- [P3] inject_fanqie_cookie.py 的 click_select 为未调用死代码 — E:/code/novel-editorial/scripts/inject_fanqie_cookie.py:95-95
  scripts/inject_fanqie_cookie.py:95 定义的 `click_select(ws_url, x, y)` 在整个仓库中无任何调用点（rg 仅命中定义行），main() 只执行 cookie 注入，属遗留死代码，应删除以免误导后续维护。

- [P3] record_work.py 失败发布日志缺 created_at，时间列恒为空 — E:/code/novel-editorial/tools/record_work.py:348-352
  tools/record_work.py:348 失败分支 `INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared)` 省略 created_at 列，而 db.py:561、record_work.py:336、publish_stock.py:264/293 其余 4 处插入均写 `datetime('now','localtime')`；schema 中 created_at DEFAULT '' 使失败记录的时间戳恒为空字符串，scripts/watch_daily.py 与面板按 id 展示该列时显示空白，且无法按时间回溯失败。

- [P3] get_meta.py 多处无保护 json.loads，脏数据即整体崩溃 — E:/code/novel-editorial/tools/get_meta.py:47-47
  tools/get_meta.py:47/101/154/155 对 `row["outline"]`、`row["protagonists"]`、`row["tags"]` 直接 `json.loads(... or "{}")` 且无 try/except；这些列由 LLM 链路与人工写入，出现非合法 JSON（旧数据、手改、n8n 遗留的 `[object Object]` 脏值）时整个 CLI 抛异常退出，n8n/调度器调用链失败且无降级输出。其余同类读取（hot_topics、reader_stats）均有保护，此处不一致。

- [P3] check_stock.py 对非法 pending_publish 设置值抛 ValueError — E:/code/novel-editorial/tools/check_stock.py:31-32
  tools/check_stock.py:31 `int(settings.get("pending_publish") or 0)` 无异常捕获，settings 表由面板/手工写入，一旦该键为非数字字符串（如 "abc"），CLI 直接崩溃且无错误信息输出，n8n/调度器调用链失败。

- [P3] delete_book.py 清理后残留 agent_messages 孤儿行 — E:/code/novel-editorial/tools/delete_book.py:66-75
  tools/delete_book.py 的 `_purge_novel`（45-76 行）按 chapter_id/novel_id 列清理子表，但 agent_messages 以 `ref_novel_id` 关联作品（无 novel_id 列），删除书籍后其消息行不会被清除；该表无 FK 约束故删除本身不报错，但留下指向已删作品的孤儿数据，get_meta/面板查询会读到悬挂引用。

- [P3] launch_desktop.vbs 不检查 electron.exe 存在，静默失败 — E:/code/novel-editorial/launch_desktop.vbs:5-7
  launch_desktop.vbs:5-7 直接拼接 `desktop\node_modules\electron\dist\electron.exe` 并 `ws.Run`，未校验文件是否存在；依赖未安装（node_modules 缺失）时 ws.Run 返回错误码但不产生任何提示，用户双击后无任何反应，难以排查。

- [P3] start_n8n.ps1 硬编码 Node.js 安装路径 — E:/code/novel-editorial/scripts/start_n8n.ps1:24-25
  scripts/start_n8n.ps1:24 硬编码 `C:\Program Files\nodejs\node.exe`，在其他 node 安装位置（便携版、nvm、非 C 盘）下 Start-Process 直接失败；该脚本是 README 标注的 n8n 异常回退入口，环境迁移后回退能力静默失效。建议从 Get-Command node 或 NODE_EXE 环境变量解析。

- [P3] n8n_api.py 触发器名硬编码且 N8N_TMP_PW 未文档化 — E:/code/novel-editorial/tools/n8n_api.py:83-84
  tools/n8n_api.py:83 `triggerToStartFrom: {"name": "每日触发"}` 与工作流触发器节点名强耦合，节点改名后 run 动作静默失败；另 line 9 `os.environ["N8N_TMP_PW"]` 使用裸索引（N8N_EMAIL 用 get），而 .env.example 未收录该变量，按示例配置运行 import 即 KeyError。

- [P3] 遗留 n8n 工作流 UTC published_at 与 preflight 本地日期比较不一致 — E:/code/novel-editorial/n8n/novel_workflow.json:1313-1313
  n8n\novel_workflow.json:1313 的 jsCode 用 `new Date().toISOString()` 写入 UTC published_at，而 tools/preflight.py `check_already_ran` 用 `date('now','localtime')` 做字符串比较：UTC+8 下本地 23:30 发布的章节存为 `2026-08-11 15:30:00`，次日 00:30 预检判定"今日未发布"（已模拟验证），回退启用 n8n 流程时会重复发布。现役链路 publish_stock.py 用 `datetime.now()` 本地时间、与预检一致，故仅为遗留回退风险。

- [P3] create_book.py/delete_book.py 的 --db 相对路径未解析到项目根 — E:/code/novel-editorial/tools/create_book.py:337-337
  tools/create_book.py:337 与 tools/delete_book.py:136 直接 `db.connect(Path(args.db))`，而同批工具（check_stock/current_book/collect_reader_stats/preflight）均有 `if not db_path.is_absolute(): db_path = ROOT / db_path` 归一化；从非仓库根目录显式传 `--db demo.db` 运行时会连接错误目录下的库（默认值 config.DB_PATH 为绝对路径，故仅显式相对路径触发），行为与其余 CLI 不一致。
