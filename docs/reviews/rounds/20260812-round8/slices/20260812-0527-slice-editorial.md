审查范围：tools/ 下 21 个目标文件（语法基线 21/21 通过；editorial_daily/workday/auto_fill_actions 等 dry-run 与针对性 SQL/幂等验证全部通过）。共发现 5 个非阻塞缺陷（2×P2、3×P3）：agent_meeting 行动项 session_id 硬编码 0、pending_publish 一次性覆盖在预检失败路径残留、mailroom 错误文案不一致、write_diaries 库调用污染 stdout、architect_weekly 本周判定边界。均不影响主流程正确性、无 P0/P1 阻塞项、无 SQL 注入/锁并发问题，可合入后按优先级修复。

Full review comments:

- [P2] agent_meeting 会后行动项硬编码 session_id=0，丢失会议关联 — E:\code\novel-editorial\tools\agent_meeting.py:736-743
  tools/agent_meeting.py:736 调用 `activity.generate_post_meeting_actions(conn, 0, weekly_id, ...)` 时把 session_id 硬编码为 0，而同一函数第 638 行刚通过 `session_id = cur.lastrowid` 创建了真实 session（meeting_sessions 行）。对比 novel_editorial/services/meeting_session.py:595，交互式会议路径传的是真实 session_id。后果：CLI/n8n 周会（agent_meeting.py 作为 n8n「开会」节点被调用）生成的 agent_actions 全部带 session_id=0，面板按会议 session 追溯/过滤会后行动项时这些任务不可见，与 web 交互式会议行为不一致。应传入第 638 行生成的 session_id。

- [P2] 预检失败路径不清零 pending_publish 一次性覆盖 — E:\code\novel-editorial\tools\editorial_daily.py:1659-1664
  tools/editorial_daily.py:1663 在 `daily(chapters=N)` 时把 `pending_publish` 设为 N，但清零（1733 行 `set_many(conn, {"pending_publish": "0"})`）只发生在 `_preflight` 通过之后；preflight 返回 skipped（1708-1714）或 ok=False（1720-1727）时提前 return，一次性覆盖残留。触发条件：手动指定章数（CLI --chapters / workday free 模式 LLM 返回 chapters）且本次预检失败（cookie 失效、预算超限、当日已发布、锁被占）。后果：下一次 scheduled 运行仍按残留的 N 章执行，破坏注释声明的 one-shot 语义，可能造成计划外发布。清零应移到 preflight 检查之前或失败路径同样执行。

- [P3] mailroom.resolve 错误消息遗漏合法 resolution 值 — E:\code\novel-editorial\tools\mailroom.py:167-167
  tools/mailroom.py:167 返回 `resolution must be accepted|rejected|done`，但模块顶部 RESOLUTIONS 实际包含 6 个合法值（accepted/rejected/done/rework/clarify/defer），且 editorial_daily._handle_outbox 与 meeting 流程确实使用 rework/clarify/defer（如 `mailroom.resolve(conn, reply_to, decision)` 传 decision 为 "rework"）。错误文案会误导调用方（如 web 面板）以为 rework/clarify/defer 被拒绝。建议文案与 RESOLUTIONS 保持一致。

- [P3] write_diaries.write 库调用时 print 污染调用方 stdout — E:\code\novel-editorial\tools\write_diaries.py:297-297
  tools/write_diaries.py:297 在 `write()` 末尾 `print(json.dumps(out, ...))` 输出到 stdout，但该函数是库入口：editorial_daily._wrapup（tools/editorial_daily.py `_run_tool(ctx, "全员写日记", lambda: write_diaries.write(...))`）和 workday._close_locked 都以库方式调用。触发条件：`python tools/editorial_daily.py` 每次运行都会在最终 result JSON 之前混入 11 个 agent 的日记 JSON 行，CLI 输出不再是合法单 JSON，机器解析（如调度器/脚本读取 stdout）会被破坏。建议库模式下仅返回 dict、由调用方决定是否打印（CLI main 里 print）。

- [P3] architect_weekly 本周章节判定在 novels.updated_at 为空时计入全部章节 — E:\code\novel-editorial\tools\architect_weekly.py:284-289
  tools/architect_weekly.py:284-289 用 `c["published_at"] >= str(row["updated_at"])[:10]` 判定「本周章节」，novels.updated_at 默认值为 ''（db.add_novel 插入时不写该列）。当 updated_at 为空时 `""[:10]` 为 ""，所有已发布章节（published_at >= "" 恒真）都被计入 chapters_this_week/words_total/avg_score，周会材料与 agent 简报数据虚高。触发条件：新建作品后未经过 apply_architect/create_book 等会写 updated_at 的流程即召开周会。建议按周界（如当前周起始）或创建时间兜底。
