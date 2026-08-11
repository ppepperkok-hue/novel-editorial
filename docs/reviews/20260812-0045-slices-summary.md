# 分片审查汇总 · 20260812-0045

## core

### P2（3）
- [P2] run_workflow_now("daily") 未启动任何任务却返回 started=True — E:\code\novel-editorial\novel_editorial\services\control.py:216-223
- [P2] _run_cli 吞掉非零退出码，周会链路步骤静默失败 — E:\code\novel-editorial\novel_editorial\services\control.py:85-97
- [P2] LLM 输出的畸形 agency/outbox 字段会让整个会议崩溃 — E:\code\novel-editorial\novel_editorial\services\meeting_session.py:294-295

### P3（2）
- [P3] _serve_static 的 startswith 前缀检查可逃逸到 dist 前缀兄弟目录 — E:\code\novel-editorial\novel_editorial\web_api.py:1021-1028
- [P3] claim_action 的 check-then-act 竞态允许同一行动项被重复认领 — E:\code\novel-editorial\novel_editorial\services\activity.py:132-144

## editorial

### P1（2）
- 1 | P1 | relations.py:56-60 / mailroom.py:163 | 日更失败、消息解析静默失效、面板数据消失 | 使用旧 schema 库（含默认 demo.db） | 实测 OperationalError |
- 2 | P1 | editorial_daily.py:1301/1066/1589 | 任务误标完成、关系/信任被改、手动档被清 | 任何 --dry-run 运行 | fresh 库实测 claimed→done |

### P2（2）
- 3 | P2 | agent_tool_loop.py:140-153 | outbox/agency 静默丢失 | 模型输出 text+outbox 混合结构 | 复现脚本确认 |
- 4 | P2 | auto_fill_actions.py:46-48 | --days 参数无效 | 传 --days 时 | 代码路径确认 |

### P3（3）
- 5 | P3 | editorial_daily.py:107-117 | 收件人未读标记丢失 | outbox 消息 + 发件人再次调用 | 代码路径确认 |
- 6 | P3 | agent_meeting.py:431-486 | 无（死代码） | — | 代码路径确认 |
- 7 | P3 | write_diaries.py:118-120 | 周记整批中断 | 历史脏 content | 代码路径确认 |

## frontend

### P1（1）
- "title": "[P1] release.js aborts before creating a release because gh release view throws when the release is missing",

### P2（2）
- "title": "[P2] AgentsPage passes .md-suffixed agent key to diary/state APIs, so diaries never load and moods never match",
- "title": "[P2] WorksPage 新书创意 panel reads fields that /api/ending/status never returns",

### P3（4）
- "title": "[P3] DashboardPage '本次发布几章' modal and runNow are unreachable dead code",
- "title": "[P3] desktop/main.js registers app:install-update IPC that preload.js never exposes",
- "title": "[P3] desktop/main.js spawns pythonw without an error handler, so a missing Python crashes the app instead of failing gracefully",
- "title": "[P3] No component tests for most pages; only 16 tests cover 12 routes",

## knowledge

### P1（1）
- [P1] 重复同步章节摘要导致 version/history 无限膨胀 — E:\code\novel-editorial\tools\novel_knowledge.py:195-208

### P2（4）
- [P2] clean_novel_knowledge 删除带 history 的 power/金手指 行触发外键崩溃 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:209-214
- [P2] 链式相似规则合并计划引用已删除行导致 --apply 崩溃 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:127-141
- [P2] 模型输出非 JSON 时知识管家静默成功（fake green） — E:\code\novel-editorial\tools\knowledge_keeper.py:135-160
- [P2] 知识包自动更新后 frontmatter updated_at 不刷新 — E:\code\novel-editorial\tools\knowledge_keeper.py:176-176

### P3（5）
- [P3] ai_taste_check 漏检全角问号连续与全角叹问组合 — E:\code\novel-editorial\tools\ai_taste_check.py:34-34
- [P3] novel_knowledge 死参数与 CLI 文档不一致 — E:\code\novel-editorial\tools\novel_knowledge.py:365-365
- [P3] prompts/ 根目录四个旧模板为死文件 — E:\code\novel-editorial\prompts\editor.md:1-1
- [P3] export_agent_prompts 导出 frontmatter 丢失 max_tokens — E:\code\novel-editorial\tools\export_agent_prompts.py:72-76
- [P3] distill_lessons 对 topics/attendees 脏 JSON 无保护 — E:\code\novel-editorial\tools\distill_lessons.py:83-89

## platform

### P1（2）
- [P1] collect_reader_stats CLI always crashes on undefined ENV_FILE — E:\code\novel-editorial\tools\collect_reader_stats.py:133-133
- [P1] delete_book local purge always fails with FK IntegrityError — E:\code\novel-editorial\tools\delete_book.py:43-52

### P2（5）
- [P2] delete_book lets URLError/HTTPError escape and crash — E:\code\novel-editorial\tools\delete_book.py:83-87
- [P2] preflight lock is stealable: recorded PID is the exiting preflight process — E:\code\novel-editorial\tools\preflight.py:122-126
- [P2] record_work crashes when chapter summary is a plain string — E:\code\novel-editorial\tools\record_work.py:222-222
- [P2] pending_publish cleared before publish attempt; request silently lost on failure — E:\code\novel-editorial\tools\publish_stock.py:363-367
- [P2] websocket-client undeclared; inject_fanqie_cookie fails in project venv — E:\code\novel-editorial\pyproject.toml:10-10

### P3（1）
- [P3] check_stock --novel-id never wired to CLI (multi-book isolation unreachable) — E:\code\novel-editorial\tools\check_stock.py:88-88

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 6 |
| P2 | 16 |
| P3 | 15 |
