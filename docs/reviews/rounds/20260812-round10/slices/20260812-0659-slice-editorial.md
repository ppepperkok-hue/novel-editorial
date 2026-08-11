审查范围：tools 下 21 个目标文件（editorial_daily/workday/editorial_steps/editorial_state/flow_graph/export_flow_html/daily_runs/auto_fill_actions/agent_context/agent_meeting/agent_tool_loop/mailroom/relations/promises/meeting_actions/meeting_kinds/meeting_materials/write_diaries/architect_weekly/apply_architect/app_settings），仅按需读取 config.py/db.py/llm_client.py 及 services/* 验证契约。基线：21 文件 python -m compileall 全部通过（exit 0）；切片相关定向 pytest 117 项全部通过；无硬编码密钥、无编码问题。已确认 4 个 P2 功能缺陷（workday 日记双写、重做失败仍标 done、_handle_agency 信封泄漏、meeting dry-run 落库）与 2 个 P3，其中 2 个 P2 为 round9 已报未修。无 P0/P1、不阻断发布链路，但现有代码并非无缺陷，建议按 P2 修复后再依赖任务板/承诺证据与 dry-run 语义。

Full review comments:

- [P2] workday 日更模式重复写日记：open 与 close 各写一遍 — E:\code\novel-editorial\tools\workday.py:277-277
  `workday.open(mode="write")` 会内联执行 `editorial_daily.daily()`，其 `_wrapup`（tools/editorial_daily.py:1443）已经调用 `write_diaries.write(conn, novel_id, "daily")`；随后 `workday.close()` 的 `_close_locked`（tools/workday.py:277）又调用一次 `write_diaries.write(conn, row["novel_id"] or 0, "daily")`，而 `write_diaries.write` 无任何去重。已在临时库复现（mock LLM + 全链）：open 后 agent_diaries=11、cost_logs=27，close 后变 22/38，即每个 agent 的日记、`cost_logs`（record_cost，重复计入月度预算闸门）和 `agent_activity` 全部翻倍；scheduler 直跑路径无此问题，workday 路径必现。建议 close 时跳过 daily 模式日记（或按 run_id/当日去重），只保留收工小结。

- [P2] 重做失败时 _settle_rework 仍把行动项标为 done（假成功） — E:\code\novel-editorial\tools\editorial_daily.py:1264-1271
  tools/editorial_daily.py:1264-1271 在 `_review_retry` 返回后无条件执行 `_settle_rework(conn, track_req)`（1287-1309），后者把留言 resolve 成 rework 并 `activity.update_action(..., status="done", result="即时重写已完成")`；但 `_review_retry` 在写手/润色/审稿任一 LLM 失败或重试后质量门仍不过时返回失败 gate。已复现：mock 让重试链全部失败，gate passed=False，行动项却变成 done。后果：任务板与 `settle_promises`/`auto_fill_actions` 会把 done 行动项当作完成证据，重做请求永久丢失。建议仅在 `gate.get("passed")` 为 True 时结算，失败保留 pending。

- [P2] _handle_agency 对散文 Agent 返回 JSON 信封而非正文 — E:\code\novel-editorial\tools\editorial_daily.py:207-207
  tools/editorial_daily.py:207 在 `_handle_agency` 弹出 agency 后无条件 `return json.dumps(obj)`，与同文件 `_handle_outbox`（170-176 已修复为只剩 text 时返回纯正文）不一致。若写手/润色（prose agent）输出 `{"text": "正文", "agency": [...]}`，管线拿到的是 `{"text": "正文"}` 信封：润色 prompt 收到 JSON 初稿、质量门按信封统计字数，若润色镜像输出则 `_publish_track` 会把被转义的 JSON 当章节发布到番茄。已复现：`_handle_agency(ctx, "润色A", '{"text":"...","agency":[...]}')` 返回 `{"text": "..."}`。建议与 `_handle_outbox` 一致：仅剩 text 时返回 `obj["text"]`。

- [P2] agent_meeting --dry-run 仍落库 actions/activity 并执行 apply_report — E:\code\novel-editorial\tools\agent_meeting.py:736-745
  tools/agent_meeting.py:736-745 把 `dry_run=args.dry_run` 传给 `activity.generate_post_meeting_actions`，但该函数（novel_editorial/services/activity.py:323-399）的 dry_run 只跳过 LLM 调用，tasks 为空时走规则兜底并无条件 `create_action`；同时 778-791 的 `apply_report`/`create_planning_from_next_book` 和每条发言的 `activity.log_activity` 都不受 dry_run 门控。已在全新临时库复现：`--dry-run --rounds 1` 写入 meeting_sessions=1、weekly_meetings=1、agent_actions=6、agent_activity=13，并把 novels.outline/updated_at 重写。这些幻影行动项会进入 agent 简报、上下文快照与承诺结算证据，与 editorial_daily/workday/write_diaries 的零写入 dry-run 语义矛盾；`test_meeting_dry_run_full_chain` 只断言 session/weekly_meetings（有意），未覆盖 actions/activity。

- [P3] architect_weekly._safe_int(None) 在缺省设置库上刷 stderr 告警 — E:\code\novel-editorial\tools\architect_weekly.py:332-333
  tools/architect_weekly.py:332-333、413 对 `settings.get("daily_chapters")` 等直接调用 `_safe_int`，而 `_safe_int`（67-76）对 None 先 `int(None)` 抛 TypeError 再打印 "note: 非整数配置，使用默认值"。agent_meeting/meeting_session 流程不调用 `app_settings.ensure_defaults`，新库/未初始化库每次开会都会向 stderr 刷 3 条误导性告警（round9 已记录，未修复）。建议 `_safe_int` 对 None/空串直接返回默认值不告警（对齐 publish_stock._safe_int_setting），或先 ensure_defaults。

- [P3] _meeting_directives 读取的 writing_directives 永无生成方，功能空转 — E:\code\novel-editorial\tools\editorial_daily.py:913-913
  tools/editorial_daily.py:913 从最新 weekly_meetings.report 读取 `writing_directives`，但 `chair_summary` 的报告 schema（tools/agent_meeting.py:538-553）只定义了 meeting_id/date/attendees/topics/discussion_summary/cover_prompt/decisions/disagreements/action_items，全仓没有任何生成方写入该字段（仅 tests/test_editorial_daily.py:307 手工注入），因此“编辑部最近共识”注入和 webapp MeetingsPage 的“写作指令”徽标在生产中永远为空。建议把 writing_directives 加入 chair_summary 的 JSON 规格并让 LLM 输出，或删除该空转分支。
