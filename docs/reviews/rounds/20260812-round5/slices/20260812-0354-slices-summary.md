# 分片审查汇总 · 20260812-0354

## core

### P2（3）
- [P2] _normalize_action_items 把 JSON 数组字符串拆成碎片任务 — E:/code/novel-editorial/novel_editorial/services/activity.py:263-273
- [P2] bind_book 先提交 DB 再写 ~/.n8n/.env，目录缺失时状态半更新 — E:/code/novel-editorial/novel_editorial/services/ending.py:51-68
- [P2] apply_schedule 跨盘符 os.path.relpath 抛 ValueError 导致 500 — E:/code/novel-editorial/novel_editorial/services/control.py:289-294

### P3（2）
- [P3] run_session 注释声称用会话库，实际忽略行的 db_path 回退 demo.db — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:324-330
- [P3] services/n8n.py 全仓库无调用方，属死代码 — E:/code/novel-editorial/novel_editorial/services/n8n.py:1-6

## editorial

### P1（1）
- [P1] workday.py 缺少 __main__ 入口，README 文档化的 CLI 静默无操作 — E:\code\novel-editorial\tools\workday.py:396-399

### P2（2）
- [P2] write_diaries --dry-run 仍执行 clean_old 删除 56 天前的日记 — E:\code\novel-editorial\tools\write_diaries.py:254-256
- [P2] _apply_writer_responses 读取错误层级，写手响应功能静默失效 — E:\code\novel-editorial\tools\editorial_daily.py:685-689

### P3（3）
- [P3] quality_gate 对非数字 score/hook_rating 直接抛异常，整次日更失败 — E:\code\novel-editorial\tools\editorial_steps.py:396-400
- [P3] merge_blueprints 对非数字 seq 抛 ValueError，周会决定整体不落盘 — E:\code\novel-editorial\tools\apply_architect.py:18-23
- [P3] meeting_actions 幂等标记先于副作用提交，副作用失败后永久不可重试 — E:\code\novel-editorial\tools\meeting_actions.py:51-53

## frontend

### P1（2）
- [P1] release.js uploads ASCII exe whose name differs from latest.yml path, breaking auto-update — E:\code\novel-editorial\desktop\release.js:44-46
- [P1] demo.db moved into resources dir; NSIS upgrade overwrites it and wipes user run data — E:\code\novel-editorial\desktop\main.js:52-55

### P2（1）
- [P2] ensureApi failure leaves the app running with no window and no tray — E:\code\novel-editorial\desktop\main.js:241-249

### P3（2）
- [P3] watchExecutions only tracks list[0], so terminal notifications can be missed — E:\code\novel-editorial\desktop\main.js:196-209
- [P3] refresh() resets refreshing flag before the fetch completes — E:\code\novel-editorial\webapp\src\App.jsx:62-65

## knowledge

### P1（1）
- "title": "[P1] sync_from_chapters 对 character_states 缺类型防御，LLM 输出数组即整批同步崩溃",

### P2（1）
- "title": "[P2] distill_lessons 的 session 分支硬编码 attendees/kind，丢弃已存参会者信息",

### P3（5）
- "title": "[P3] clean_novel_knowledge 的 --dry-run 参数从未读取，属死参数",
- "title": "[P3] clean_novel_knowledge 备份文件名硬编码 demo- 前缀",
- "title": "[P3] sync_latest 的 DISTINCT+ORDER BY 依赖 SQLite 未定义行为",
- "title": "[P3] 冲突草稿按 title 去重，跨小说同名实体漏建草稿",
- "title": "[P3] knowledge_keeper/distill_lessons 对 usage 字段无空值防御",

## platform

### P2（1）
- "title": "[P2] create_book 的 _gender 把「仙侠言情」永远判为男频",

### P3（5）
- "title": "[P3] collect_reader_stats 从环境变量读 FANQIE_BOOK_ID，与 current_book 的 DB 权威设计矛盾",
- "title": "[P3] record_work CLI 硬编码 demo.db，缺少 --db 参数",
- "title": "[P3] preflight.py 的 --no-lock 参数声明后从未被读取",
- "title": "[P3] install_autostart.ps1 用 ASCII 写 VBS，非 ASCII 路径会被替换为 ?",
- "title": "[P3] 当前 .venv 缺 websocket-client，inject_fanqie_cookie.py 无法运行",

## tests

### P3（5）
- [P3] compliance 空词库告警逻辑与真实数据文件均无测试守护 — E:\code\novel-editorial\tests\test_compliance.py:23-29
- [P3] .env.example 遗漏被实际消费的 REVIEW_RETRY_MAX 与 MEETING_HEARTBEAT_TIMEOUT_MINUTES — E:\code\novel-editorial\.env.example:1-81
- [P3] .env.example 四个死配置键误导用户（MONTHLY_BUDGET/N8N_HOST/N8N_LISTEN_ADDRESS/N8N_PASSWORD） — E:\code\novel-editorial\.env.example:24-24
- [P3] quality_gate 加载 ai_flavor 缺 isinstance 校验，字符串值会按单字符计 AI 味密度 — E:\code\novel-editorial\novel_editorial\quality_gate.py:20-25
- [P3] compliance._read_custom_words 无异常捕获，坏编码词库文件直接穿透发布前扫描 — E:\code\novel-editorial\novel_editorial\compliance.py:62-71

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 4 |
| P2 | 8 |
| P3 | 22 |
