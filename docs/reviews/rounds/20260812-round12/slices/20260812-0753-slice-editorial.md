Scope: 21 files under tools/ (editorial_daily, workday, editorial_steps/state, flow_graph, export_flow_html, daily_runs, auto_fill_actions, agent_context/meeting/tool_loop, mailroom, relations, promises, meeting_actions/kinds/materials, write_diaries, architect_weekly, apply_architect, app_settings). Baseline: python -m compileall passes on all slice files; targeted pytest on slice-related suites passed 216/216 (test_editorial_daily, test_workday, test_editorial_steps, test_editorial_state, test_flow_graph, test_export_flow_html, test_daily_runs, test_auto_fill_actions, test_agent_context, test_agent_tool_loop, test_agent_meeting, test_mailroom, test_relations, test_promises, test_meeting_actions, test_meeting_materials, test_agent_actions, test_meeting_session). No P0/P1 findings; no hardcoded secrets, SQL placeholder mistakes, or lock/concurrency defects found. All six findings are non-blocking P2/P3; the two P2 items (review-tone lookup direction mismatch, n8n sync status staleness) are silent behavioral defects worth fixing in the next cycle.

Full review comments:

- [P2] _review_tone 查询方向与写入方向相反，摩擦语气永不生效 — E:\code\novel-editorial\tools\editorial_daily.py:944-959
  tools/editorial_daily.py:948-954 的 `_review_tone` 用 `agent=写手 AND other=审稿` 查摩擦值，但所有关系写入都是反方向：`_rel(conn, 审稿X, 写手X, ...)`（1153-1155、1205-1210、1227-1232、1271-1277 行）写入的是 agent=审稿、other=写手 的行，且全仓库没有任何 `(写手→审稿)` 方向的事件写入。已用内存库复现：插入 (agent='reviewer', other='writer', friction=0.5) 后按 `_review_tone(conn,'writer','reviewer',1)` 的查询执行，返回 None（摩擦按 0 处理），反向查询才命中。结果是 R2-1-3 的拒稿语气调节永远走「你们关系不错，语气平和些」分支，摩擦 >=0.3 的严厉措辞从不出现；修复需统一查询/写入方向。

- [P2] sync_from_n8n 不更新已导入运行的状态，成功运行被误标为失败 — E:\code\novel-editorial\tools\daily_runs.py:110-116
  tools/daily_runs.py:110-116 对已存在的 run_id 直接 `continue`，从不更新状态；若 n8n 执行在首次同步时仍是 running，之后即使成功完成，本地 daily_runs 也会一直停留在 running，直到 tools/daily_runs.py:226-245 的 recover_stale_runs 在 12 小时后把 `status='running'` 的行按「进程中断或超时（孤儿恢复）」翻成 failed。现有 test_daily_runs 只验证第二次同步 written=0（幂等），未覆盖状态回填。结果：面板会把实际成功的 n8n 运行显示为失败，n8n-legacy 行的最终状态永远不准确。建议对已存在行做状态/时间戳的增量 UPDATE。

- [P3] agent_meeting --dry-run 仍会落库伪造的会议记录 — E:\code\novel-editorial\tools\agent_meeting.py:626-639
  tools/agent_meeting.py:626-639 创建 meeting_sessions、701-715 插入 weekly_meetings、717-726 更新 session 状态，均未受 `not args.dry_run` 保护。已复现：对 demo.db 的拷贝执行 `python tools/agent_meeting.py --db <copy> --dry-run --rounds 1` 后，库中新增 status='finished' 的 meeting_sessions 行和 status='completed' 的 weekly_meetings 行，内容为 [dry-run] 占位发言；这与同文件 write_diaries、apply_report 的 dry-run 不落盘语义不一致，会污染面板会议列表与统计。建议整个 session+archive 段在 dry_run 时跳过。

- [P3] compress_history 从未被调用，历史压缩功能是死代码 — E:\code\novel-editorial\tools\agent_meeting.py:280-308
  tools/agent_meeting.py:280-308 定义了增量历史压缩（compress_history），但全仓库除定义外没有任何调用点（grep 仅命中定义行）；main() 调用 round_speech 时（645-648 行）不传 compressed_history，该参数恒为空，实际提示只展示 transcript[-2:] 最近两条。模块文档宣称的「每轮压缩新增发言」从未生效，长会议上下文会持续膨胀，且该函数还带 dry_run/mock 参数，属于未接线的死代码。要么在 main() 的轮次循环中接入，要么删除该函数及其文档。

- [P3] daily(chapters=N) 在生成链上不生效，请求 1 章仍产出 2 章 — E:\code\novel-editorial\tools\editorial_daily.py:1670-1685
  tools/editorial_daily.py:1709-1716 把 chapters 写入 pending_publish，check_stock 据此算 target；但当存稿不足走 _generate 分支时，1670-1685 无条件跑 A/B 两条轨道（parse_planner_outline 也强制至少 2 章），target 仅用于返回值且被 daily() 丢弃（`_target` 未使用）。复现路径：--chapters 1 且存稿为 0 时，一次运行发布 2 章但报告 target=1，与 CLI 帮助文案「本次发布章数（默认读设置）」不符，并多花一次 LLM/发布成本。若 A/B 双轨是刻意设计，应把参数语义改为「至少 N 章」或在帮助文本中注明生成链固定双章。

- [P3] 切片内 5 个工具模块缺少直接单元测试 — E:\code\novel-editorial\tools\apply_architect.py:214-217
  tests/ 下没有覆盖 apply_architect.py（merge_blueprints/apply_report/create_planning_from_next_book）、architect_weekly.py（build_materials/build_planning_materials）、write_diaries.py（write/daily_payload/weekly_payload）、app_settings.py、meeting_kinds.py 的测试文件（grep tests/ 无对应 import）；这些模块承担周会结论落盘、会议材料、全员日记/心情与承诺结算等关键副作用。F3（dry-run 落库）这类问题正是由于缺少对 dry-run 语义的断言才漏掉的。建议至少为 apply_report 的幂等/完结分支与 write_diaries.write 的 dry-run 不落盘语义补测试。
