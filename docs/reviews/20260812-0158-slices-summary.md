# 分片审查汇总 · 20260812-0158

## core

### P1（1）
- [P1] Scheduler control hardcodes ROOT/demo.db, diverging from the panel's --db target — E:\code\novel-editorial\novel_editorial\services\control.py:108-119

### P2（1）
- [P2] Reminder daemon polls every 30 min but only fires on an exact-minute match — E:\code\novel-editorial\novel_editorial\services\reminders.py:126-143

### P3（3）
- [P3] /api/knowledge_drafts distill branch leaks a SQLite connection per request — E:\code\novel-editorial\novel_editorial\web_api.py:920-929
- [P3] hot_topics.json written non-atomically and read without error handling — E:\code\novel-editorial\novel_editorial\hot_topics.py:285-288
- [P3] CLI entry points default --db to relative 'demo.db', silently using a different database outside ROOT — E:\code\novel-editorial\novel_editorial\scheduler.py:101-104

## editorial

### P1（1）
- [P1] Unwrap dispatch envelope before writer-response round and note injection — E:\code\novel-editorial\tools\editorial_daily.py:1607-1609

### P2（3）
- [P2] Mark produce-skipped workdays as skipped so close() does not report failed — E:\code\novel-editorial\tools\workday.py:276-288
- [P2] Gate diary/meeting dry-run writes so moods and old diaries survive — E:\code\novel-editorial\tools\write_diaries.py:180-196
- [P2] Return unwrapped prose from _handle_outbox instead of the JSON envelope — E:\code\novel-editorial\tools\editorial_daily.py:154-160

### P3（1）
- [P3] Guard json.loads in latest_weekly/mood_of against dirty diary rows — E:\code\novel-editorial\tools\agent_meeting.py:115-129

## frontend

### P1（1）
- [P1] 打包版桌面端 UI 与后台运行使用两个不同的 SQLite 数据库 — E:\code\novel-editorial\desktop\main.js:51-61

### P2（1）
- [P2] API 启动失败时桌面端无任何可见错误提示，直接静默退出 — E:\code\novel-editorial\desktop\main.js:217-223

### P3（5）
- [P3] release.js 对同一版本重复执行必然中断，与注释宣称的幂等不符 — E:\code\novel-editorial\desktop\release.js:45-46
- [P3] 命令面板缺少 flow 与 editorial 两个页面入口 — E:\code\novel-editorial\webapp\src\components\CommandPalette.jsx:4-15
- [P3] WorksPage 对 tags 直接 JSON.parse 无防护，非 JSON 会炸掉整页 — E:\code\novel-editorial\webapp\src\components\WorksPage.jsx:259-260
- [P3] ui.jsx 的 fmtMoney 是无引用死代码 — E:\code\novel-editorial\webapp\src\components\ui.jsx:25-29
- [P3] desktop 目录完全没有自动化测试 — E:\code\novel-editorial\desktop\package.json:6-11

## knowledge

（本分片无显式 P0-P3 条目）

## platform

### P2（1）
- [P2] rename_on_login.ps1 会在重命名前杀死自身进程 — E:/code/novel-editorial/scripts/rename_on_login.ps1:30-33

### P3（13）
- [P3] n8n_api.py 登录响应无 Set-Cookie 时抛 TypeError 而非 RuntimeError — E:/code/novel-editorial/tools/n8n_api.py:23-23
- [P3] preflight.py 的 --no-lock 参数定义后从未被读取 — E:/code/novel-editorial/tools/preflight.py:199-203
- [P3] publish_stock.py 存在不可达的 finished 死分支 — E:/code/novel-editorial/tools/publish_stock.py:352-354
- [P3] inject_fanqie_cookie.py 的 click_select 为未调用死代码 — E:/code/novel-editorial/scripts/inject_fanqie_cookie.py:95-95
- [P3] record_work.py 失败发布日志缺 created_at，时间列恒为空 — E:/code/novel-editorial/tools/record_work.py:348-352
- [P3] get_meta.py 多处无保护 json.loads，脏数据即整体崩溃 — E:/code/novel-editorial/tools/get_meta.py:47-47
- [P3] check_stock.py 对非法 pending_publish 设置值抛 ValueError — E:/code/novel-editorial/tools/check_stock.py:31-32
- [P3] delete_book.py 清理后残留 agent_messages 孤儿行 — E:/code/novel-editorial/tools/delete_book.py:66-75
- [P3] launch_desktop.vbs 不检查 electron.exe 存在，静默失败 — E:/code/novel-editorial/launch_desktop.vbs:5-7
- [P3] start_n8n.ps1 硬编码 Node.js 安装路径 — E:/code/novel-editorial/scripts/start_n8n.ps1:24-25
- [P3] n8n_api.py 触发器名硬编码且 N8N_TMP_PW 未文档化 — E:/code/novel-editorial/tools/n8n_api.py:83-84
- [P3] 遗留 n8n 工作流 UTC published_at 与 preflight 本地日期比较不一致 — E:/code/novel-editorial/n8n/novel_workflow.json:1313-1313
- [P3] create_book.py/delete_book.py 的 --db 相对路径未解析到项目根 — E:/code/novel-editorial/tools/create_book.py:337-337

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 3 |
| P2 | 6 |
| P3 | 22 |
