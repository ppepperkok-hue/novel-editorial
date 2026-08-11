# 分片审查汇总 · 20260812-0527

## core

### P3（2）
- [P3] sync_error 字段未在前端消费，n8n 同步失败仍对用户静默 — E:\code\novel-editorial\novel_editorial\web_api.py:150-154
- [P3] _run_locked 的 RuntimeError 不落盘，会议错误对用户不可感知 — E:\code\novel-editorial\novel_editorial\services\meeting_session.py:357-360

## editorial

### P2（2）
- [P2] agent_meeting 会后行动项硬编码 session_id=0，丢失会议关联 — E:\code\novel-editorial\tools\agent_meeting.py:736-743
- [P2] 预检失败路径不清零 pending_publish 一次性覆盖 — E:\code\novel-editorial\tools\editorial_daily.py:1659-1664

### P3（3）
- [P3] mailroom.resolve 错误消息遗漏合法 resolution 值 — E:\code\novel-editorial\tools\mailroom.py:167-167
- [P3] write_diaries.write 库调用时 print 污染调用方 stdout — E:\code\novel-editorial\tools\write_diaries.py:297-297
- [P3] architect_weekly 本周章节判定在 novels.updated_at 为空时计入全部章节 — E:\code\novel-editorial\tools\architect_weekly.py:284-289

## frontend

（本分片无显式 P0-P3 条目）

## knowledge

### P1（1）
- [P1] sync_latest 对非法 JSON outline 无防御，知识库同步整体中断 — E:\code\novel-editorial\tools\novel_knowledge.py:615-615

### P2（3）
- [P2] 知识管家/蒸馏对 LLM 输出数组元素类型零校验，字符串元素直接 AttributeError 崩溃 — E:\code\novel-editorial\tools\knowledge_keeper.py:160-161
- [P2] distill_lessons 对无 lessons 键的合法 JSON 返回 ok:True，假绿灯 — E:\code\novel-editorial\tools\distill_lessons.py:178-182
- [P2] clean_novel_knowledge 在 WAL 模式下用 shutil.copy2 备份，备份文件缺失已提交数据 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:309-312

### P3（1）
- [P3] ai_taste_check.detect 空文本返回值缺少 chars 键，输出 schema 不一致 — E:\code\novel-editorial\tools\ai_taste_check.py:70-72

## platform

### P1（1）
- [P1] get_meta 对 bible.characters 非 dict 元素崩溃，日更上下文静默丢失 — E:/code/novel-editorial/tools/get_meta.py:133-136

### P2（2）
- [P2] record_work 对非 int words/prompt_tokens 崩溃导致整次归档失败 — E:/code/novel-editorial/tools/record_work.py:306-307
- [P2] record_work 同 run_id 重复归档产生重复伏笔/演化/事件行 — E:/code/novel-editorial/tools/record_work.py:235-242

### P3（3）
- [P3] check_stock 默认分支不识别 finishing 状态书，收尾期查存稿返回空 — E:/code/novel-editorial/tools/check_stock.py:48-51
- [P3] preflight CLI 在未持有运行锁时消费 manual_run_requested — E:/code/novel-editorial/tools/preflight.py:253-258
- [P3] publish_stock CLI 入口不检查运行锁，可绕过防双发保护 — E:/code/novel-editorial/tools/publish_stock.py:357-361

## tests

### P3（4）
- [P3] README 测试数量过时：写 448 个，实际 487 个 — E:\code\novel-editorial\README.md:19-19
- [P3] 测试输出被被测代码的 print 污染，建议 TextTestRunner 开 buffer — E:\code\novel-editorial\run_tests.py:18-18
- [P3] n8n 工作流硬编码 AI 味词表与 ai_words.json 存在同步漂移风险 — E:\code\novel-editorial\ai_words.json:1-13
- [P3] webapp 测试覆盖偏浅：dashboard 测试只覆盖 helper 未覆盖页面渲染 — E:\code\novel-editorial\webapp\src\__tests__\dashboard.test.jsx:1-12

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 2 |
| P2 | 7 |
| P3 | 13 |
