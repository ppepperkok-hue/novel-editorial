# 分片审查汇总 · 20260812-0753

## core

（本分片无显式 P0-P3 条目）

## editorial

### P2（2）
- [P2] _review_tone 查询方向与写入方向相反，摩擦语气永不生效 — E:\code\novel-editorial\tools\editorial_daily.py:944-959
- [P2] sync_from_n8n 不更新已导入运行的状态，成功运行被误标为失败 — E:\code\novel-editorial\tools\daily_runs.py:110-116

### P3（4）
- [P3] agent_meeting --dry-run 仍会落库伪造的会议记录 — E:\code\novel-editorial\tools\agent_meeting.py:626-639
- [P3] compress_history 从未被调用，历史压缩功能是死代码 — E:\code\novel-editorial\tools\agent_meeting.py:280-308
- [P3] daily(chapters=N) 在生成链上不生效，请求 1 章仍产出 2 章 — E:\code\novel-editorial\tools\editorial_daily.py:1670-1685
- [P3] 切片内 5 个工具模块缺少直接单元测试 — E:\code\novel-editorial\tools\apply_architect.py:214-217

## frontend

### P2（1）
- [P2] 桌面版锁文件仍写入安装目录，未随 NOVEL_DATA_DIR 迁移，只读安装导致应用拒绝启动 — E:\code\novel-editorial\desktop\main.js:82-93

### P3（3）
- [P3] release.js 的陈旧版本检查在 gh 失败时静默失效，可能重建同版本 Release — E:\code\novel-editorial\desktop\release.js:83-89
- [P3] CommandPalette 触发 run-daily/run-weekly 后不刷新面板数据，与其它操作不一致 — E:\code\novel-editorial\webapp\src\components\CommandPalette.jsx:63-72
- [P3] 桌面端 api-error IPC 与 preload closeToTray 均为无消费方的死代码 — E:\code\novel-editorial\desktop\main.js:127-143

## knowledge

### P1（2）
- [P1] upsert_ex 并发更新时重复写入 history，审计链被污染 — E:\code\novel-editorial\tools\novel_knowledge.py:230-237
- [P1] clean_novel_knowledge 链式相似规则合并时静默丢失整行内容 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:194-201

### P2（1）
- [P2] clean_novel_knowledge 删除无 item 对应的 power/金手指，唯一设定记录丢失 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:266-274

### P3（4）
- [P3] distill_lessons 对 report/transcript 的非预期 JSON 类型无防御，直接崩溃 — E:\code\novel-editorial\tools\distill_lessons.py:86-104
- [P3] upsert_ex 合并判定基于截断 120 字符的 content，长内容相似实体永不合并 — E:\code\novel-editorial\tools\novel_knowledge.py:195-195
- [P3] knowledge_keeper 对非 market 文件的 auto_updates 静默跳过，无日志无审计 — E:\code\novel-editorial\tools\knowledge_keeper.py:242-243
- [P3] export_agent_prompts 在 proxy 模式下以退出码 1 结束，脚本化调用会误判失败 — E:\code\novel-editorial\tools\export_agent_prompts.py:63-68

## platform

### P2（3）
- [P2] upsert_novel merges a new book into an older same-title novel — E:\code\novel-editorial\tools\record_work.py:68-71
- [P2] publish_batch alerts.log writes lack OSError protection — E:\code\novel-editorial\tools\publish_stock.py:298-303
- [P2] preflight.alert is unprotected while sibling helpers swallow OSError — E:\code\novel-editorial\tools\preflight.py:54-56

### P3（5）
- [P3] create_book has no idempotency after network errors — E:\code\novel-editorial\tools\create_book.py:342-344
- [P3] n8n_api.py crashes with IndexError when run without arguments — E:\code\novel-editorial\tools\n8n_api.py:96-97
- [P3] .env parsing in inject_fanqie_cookie.py / start_n8n.ps1 diverges from config.load_env — E:\code\novel-editorial\scripts\inject_fanqie_cookie.py:17-21
- [P3] acquire_lock can wedge forever on PID reuse (no age fallback) — E:\code\novel-editorial\tools\preflight.py:153-156
- [P3] check_stock counts whole-library stock when no active book — E:\code\novel-editorial\tools\check_stock.py:37-43

## tests

### P3（2）
- [P3] .env.example 未记录 NOVEL_DATA_DIR 环境变量 — E:\code\novel-editorial\.env.example:56-63
- [P3] 缺少守护 .env.example 与 config 契约的回归测试 — E:\code\novel-editorial\run_tests.py:10-19

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 2 |
| P2 | 7 |
| P3 | 18 |
