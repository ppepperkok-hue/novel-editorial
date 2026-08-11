# 分片审查汇总 · 20260812-0659

## core

### P2（1）
- [P2] hot_topics.refresh 固定临时文件名并发写盘竞态 — E:\code\novel-editorial\novel_editorial\hot_topics.py:287-291

### P3（5）
- [P3] load_meetings 的 topics 字段 JSON 解析缺少容错 — E:\code\novel-editorial\novel_editorial\services\misc.py:136-136
- [P3] write_knowledge 仅校验 title/source/updated_at，type 可注入换行破坏 frontmatter — E:\code\novel-editorial\novel_editorial\services\knowledge.py:82-87
- [P3] POST /api/knowledge save 中 write_knowledge 的 ValueError 未捕获，返回 500 — E:\code\novel-editorial\novel_editorial\web_api.py:911-911
- [P3] bind_book 的 book_id 未清洗换行，可向 ~/.n8n/.env 注入额外配置行 — E:\code\novel-editorial\novel_editorial\services\ending.py:51-57
- [P3] 会议 outbox 单条消息 chapter_id/reply_to 非整数会丢弃该 agent 全部外发邮件 — E:\code\novel-editorial\novel_editorial\services\meeting_session.py:311-312

## editorial

### P2（4）
- [P2] workday 日更模式重复写日记：open 与 close 各写一遍 — E:\code\novel-editorial\tools\workday.py:277-277
- [P2] 重做失败时 _settle_rework 仍把行动项标为 done（假成功） — E:\code\novel-editorial\tools\editorial_daily.py:1264-1271
- [P2] _handle_agency 对散文 Agent 返回 JSON 信封而非正文 — E:\code\novel-editorial\tools\editorial_daily.py:207-207
- [P2] agent_meeting --dry-run 仍落库 actions/activity 并执行 apply_report — E:\code\novel-editorial\tools\agent_meeting.py:736-745

### P3（2）
- [P3] architect_weekly._safe_int(None) 在缺省设置库上刷 stderr 告警 — E:\code\novel-editorial\tools\architect_weekly.py:332-333
- [P3] _meeting_directives 读取的 writing_directives 永无生成方，功能空转 — E:\code\novel-editorial\tools\editorial_daily.py:913-913

## frontend

（本分片无显式 P0-P3 条目）

## knowledge

（本分片无显式 P0-P3 条目）

## platform

### P2（3）
- [P2] publish_stock 部分发布成功后仍清零 pending_publish，剩余章节静默丢失 — E:\code\novel-editorial\tools\publish_stock.py:427-433
- [P2] check_stock 默认按全库统计存稿，与 publish_stock 的活跃书范围不一致 — E:\code\novel-editorial\tools\check_stock.py:25-30
- [P2] collect_reader_stats 把缺失的完读/追读率写成 0.0，误导低质章节反馈 — E:\code\novel-editorial\tools\collect_reader_stats.py:135-144

### P3（3）
- [P3] get_meta 读取非对象结构的 hot_topics.json 时 AttributeError 崩溃 — E:\code\novel-editorial\tools\get_meta.py:74-86
- [P3] release_lock 不校验锁归属，可误删并发运行持有的锁 — E:\code\novel-editorial\tools\release_lock.py:17-22
- [P3] _run_fix_worker.ps1 未转义任务文本中的双引号，可破坏 node 命令行 — E:\code\novel-editorial\scripts\_run_fix_worker.ps1:34-50

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 0 |
| P2 | 8 |
| P3 | 10 |
