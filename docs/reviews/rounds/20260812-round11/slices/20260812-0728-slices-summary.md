# 分片审查汇总 · 20260812-0728

## core

### P2（1）
- [P2] create_session 并发竞态可创建多个 running 会议会话 — E:\code\novel-editorial\novel_editorial\services\meeting_session.py:31-54

### P3（1）
- [P3] DEPRECATED 模块无生产调用方，与新链路双轨并存 — E:\code\novel-editorial\novel_editorial\pipeline.py:1-5

## editorial

### P1（1）
- [P1] Publish gate-bypass: rework failure returns original passed gate with failed rewrite text — E:/code/novel-editorial/tools/editorial_daily.py:1160-1160

### P2（1）
- [P2] Workday active-run guard bypassed by org/meeting modes, allowing two concurrent workdays — E:/code/novel-editorial/tools/workday.py:110-121

### P3（5）
- [P3] Global (novel_id=0) messages are injected but never marked read — E:/code/novel-editorial/tools/editorial_daily.py:218-235
- [P3] 'completed_with_pending' status renders as idle in exported flow report — E:/code/novel-editorial/tools/export_flow_html.py:71-88
- [P3] CLI topic/planning meetings run with weekly agenda labels in prompts — E:/code/novel-editorial/tools/agent_meeting.py:618-621
- [P3] Workday stuck forever when process dies during 'opening' phase — E:/code/novel-editorial/tools/workday.py:239-239
- [P3] Dead code: compress_history is never called — E:/code/novel-editorial/tools/agent_meeting.py:280-280

## frontend

### P2（3）
- F1 | desktop/main.js, config.py, package.json | per-machine / read-only install dir | hot-topics, weekly lock, exports, alerts silently fail; UI reports success | P2 |
- F2 | desktop/release.js, package.json, main.js | version not manually bumped | auto-update channel permanently stale | P2 |
- F3 | webapp/src/components/AgentsPage.jsx | edit mood → switch agent → save | wrong agent’s mood persisted & injected into prompts | P2 |

### P3（3）
- F4 | desktop/main.js | 3 API crashes in one session | auto-restart permanently disabled | P3 |
- F5 | desktop/main.js, config.py | inline # comment on PANEL_TOKEN line | tray triggers rejected with 403 | P3 |
- F6 | webapp/src/components/* | n/a | regression risk; no coverage for session/SSE/flow logic | P3 |

## knowledge

### P2（1）
- [P2] export_agent_prompts.py 在 proxy 模式下永不导出却返回成功 — E:\code\novel-editorial\tools\export_agent_prompts.py:63-68

### P3（5）
- [P3] ai_taste_check 四字排比启发式对普通叙述误报、对真实排比漏报 — E:\code\novel-editorial\tools\ai_taste_check.py:94-107
- [P3] distill_lessons 收到空 lessons 列表时静默返回成功 — E:\code\novel-editorial\tools\distill_lessons.py:265-270
- [P3] ai_taste_check 漏检常见写法"不是……而是"（双省略号） — E:\code\novel-editorial\tools\ai_taste_check.py:30-30
- [P3] novel_knowledge.get() 的 entity 参数未转义 LIKE 通配符 — E:\code\novel-editorial\tools\novel_knowledge.py:251-253
- [P3] knowledge_keeper 未校验 LLM 输出的 JSON schema — E:\code\novel-editorial\tools\knowledge_keeper.py:196-202

## platform

### P2（1）
- [P2] create_book 对字符串形状 protagonists 抛未捕获 AttributeError — E:\code\novel-editorial\tools\create_book.py:271-272

### P3（4）
- [P3] preflight CLI 的 already_ran 为全局检查，与 per-book 声明不一致 — E:\code\novel-editorial\tools\preflight.py:227-227
- [P3] publish_stock db.connect 失败时运行锁残留且异常裸奔 — E:\code\novel-editorial\tools\publish_stock.py:379-388
- [P3] record_work 章节 status 缺失时默认 published，产生虚假成功发布记录 — E:\code\novel-editorial\tools\record_work.py:356-356
- [P3] collect_reader_stats 仅拉取第一页 200 章，超长书无翻页 — E:\code\novel-editorial\tools\collect_reader_stats.py:69-69

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 1 |
| P2 | 7 |
| P3 | 18 |
