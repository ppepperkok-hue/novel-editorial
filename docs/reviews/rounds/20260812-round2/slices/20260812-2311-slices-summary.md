# 分片审查汇总 · 20260812-2311

## core

### P1（3）
- F1a | P1 | services/control.py:242 + tools/workday.py/tools/publish_stock.py | 桌面部署（NOVEL_DATA_DIR 设置）下 scheduled task 与手动发布并发 | 运行锁互斥失效，重复发布风险（锁的设计初衷即防此） |
- F1b | P1 | services/control.py:230-243 | 安装目录只读 + 触发周会 | acquire_lock 抛 OSError，线程静默崩溃，面板假绿灯，无任何日志 |
- "title": "[P1] 统一运行锁路径到 config.TMP_DIR，避免桌面模式下互斥失效与周会静默崩溃",

### P2（2）
- F2 | P2 | config.py:31 | NOVEL_DATA_DIR 模式直跑 web_api/desktop.py（无 --db） | DB 写安装目录（只读时失败），数据与运行时产物分离 |
- "title": "[P2] config.DB_PATH 应随 NOVEL_DATA_DIR 迁移到 RUNTIME_ROOT",

### P3（2）
- F3 | P3 | services/meeting_session.py:134 | free 会话 worker 异常死亡 | 会话永久 running，阻塞新会议直至进程重启 |
- "title": "[P3] free 会议死会话缺少运行中恢复：心跳清理跳过 free 模式且仅启动时执行",

## editorial

（本分片无显式 P0-P3 条目）

## frontend

### P2（1）
- [P2] SettingsPage 后端不可用时渲染空白页，ErrorState 被短路 — E:\code\novel-editorial\webapp\src\pages\SettingsPage.jsx:39-39

### P3（4）
- [P3] WorksPage 知识库 tab 首次进入永远显示加载中 — E:\code\novel-editorial\webapp\src\pages\WorksPage.jsx:35-45
- [P3] vite manualChunks 的 react 条目生成空 chunk，主包未拆分 — E:\code\novel-editorial\webapp\vite.config.js:26-29
- [P3] TitleBar 最大化图标状态在系统级最大化时不更新 — E:\code\novel-editorial\webapp\src\components\layout\titlebar.jsx:12-20
- [P3] desktop watchExecutions 的 notifiedExecKeys 无界增长 — E:\code\novel-editorial\desktop\main.js:303-311

## knowledge

（本分片无显式 P0-P3 条目）

## platform

### P1（1）
- [P1] get_meta.py 硬编码 ROOT 运行时路径，NOVEL_DATA_DIR 下与写入方分裂导致静默丢数据 — E:\code\novel-editorial\tools\get_meta.py:82-84

### P2（2）
- [P2] create_book.py 异常元组漏掉 OSError/socket.timeout，建书超时崩溃且不写 pending 痕迹 — E:\code\novel-editorial\tools\create_book.py:495-503
- [P2] delete_book._purge_novel 回复链清理被 ref_chapter_id 删除提前破坏，留下孤儿消息 — E:\code\novel-editorial\tools\delete_book.py:81-86

### P3（2）
- [P3] collect_reader_stats.load_env 未剥离行内注释，与 config/preflight 的 env 解析不一致 — E:\code\novel-editorial\tools\collect_reader_stats.py:48-51
- [P3] 运行锁目录在 NOVEL_DATA_DIR 下与调度器分裂，并发互斥与 release_lock 失效 — E:\code\novel-editorial\tools\publish_stock.py:378-378

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 4 |
| P2 | 5 |
| P3 | 8 |
