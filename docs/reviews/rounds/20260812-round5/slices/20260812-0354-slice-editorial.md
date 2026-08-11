审查范围：tools 下 21 个指定文件 + 契约依赖（novel_editorial/db.py、config.py、llm_client.py、services/audit.py、activity.py、meeting_session.py、tools/preflight.py、check_stock.py、current_book.py、publish_stock.py）。基线：`python -m compileall` 对 21 个文件全部通过；editorial_daily.py --dry-run 在临时库全链跑通（completed，published=2）；export_flow_html.py、app_settings.py 正常运行。发现 1 个 P1（workday CLI 缺 __main__ 入口，README 文档化命令静默无操作、exit 0）、2 个 P2（write_diaries --dry-run 删除旧日记数据；_apply_writer_responses 与 dispatch envelope 结构不匹配导致 R1-1 写手响应静默失效）、3 个 P3（quality_gate/merge_blueprints 对 LLM 输出缺类型容错；meeting_actions 幂等标记先于副作用导致失败不可重试）。P1 的静默失败与 P2 的数据删除/功能失效应在合入前修复，故该切片当前状态不正确。

Full review comments:

- [P1] workday.py 缺少 __main__ 入口，README 文档化的 CLI 静默无操作 — E:\code\novel-editorial\tools\workday.py:396-399
  `tools/workday.py` 定义了 `main()` 和 argparse CLI，但文件末尾（第 399 行 `conn.close()`）之后没有 `if __name__ == "__main__": main()`（已用 `text.count('if __name__') == 0` 验证）。因此 README.md:184-185 文档化的命令 `python tools/workday.py --action open --mode write --dry-run` 只执行模块级 import，不运行任何逻辑，退出码为 0 且无任何输出——用户按文档操作会得到一个"成功"假象，实际没有创建 daily_runs 行、没有锁、没有 produce。复现：`python tools/workday.py --action open --db demo.db --dry-run` → 无 stdout/stderr，exit 0；同一逻辑经 `import tools.workday; workday.main()` 调用则正常返回结果。库调用路径（control.py 等）不受影响，但 CLI 入口属于静默失败，需补上入口守卫。

- [P2] write_diaries --dry-run 仍执行 clean_old 删除 56 天前的日记 — E:\code\novel-editorial\tools\write_diaries.py:254-256
  `write()` 末尾的 `clean_old(conn)`（write_diaries.py:256）不检查 `dry_run`，而 `--dry-run` 的其余写入（agent_diaries INSERT、agent_states、agent_memories、cost_logs、settle_promises）都有 `if not dry_run` 守卫。复现：在临时库中插入一条 created_at=2026-06-01 的 agent_diaries 行，调用 `write_diaries.write(conn, 1, 'daily', dry_run=True)` 后该行被删除（已实测验证）。dry-run 承诺零副作用，这里却会真实删除 56 天前的日记数据；应把 `clean_old(conn)` 也放进 `if not dry_run` 分支。

- [P2] _apply_writer_responses 读取错误层级，写手响应功能静默失效 — E:\code\novel-editorial\tools\editorial_daily.py:685-689
  `_dispatch()` 返回 envelope `{"mode", "dispatch", "degraded"}`，assignments 位于 `dispatch["dispatch"]["assignments"]`（editorial_daily.py:647），但 `_apply_writer_responses()` 读取顶层 `dispatch.get("assignments")`（editorial_daily.py:687），恒为 None，于是直接 `return dispatch`——daily() 第 1685-1687 行调用它时，R1-1 写手 accept/reject/counter 响应（`TASK_RESPONSE_MODE` 默认 "on"）从不执行，也没有任何 warning/audit 提示。对比 `_writer_dispatch_notes`（第 413-417 行）已正确解包 `dispatch.get("dispatch")`，说明这是 envelope 重构时的遗漏。修复应在 `_apply_writer_responses` 内先按同样方式解包 envelope 再取 assignments。

- [P3] quality_gate 对非数字 score/hook_rating 直接抛异常，整次日更失败 — E:\code\novel-editorial\tools\editorial_steps.py:396-400
  editorial_steps.py:399 `float(reader.get("score") or 0)` 和 `float(reader.get("hook_rating") or 0)` 未做类型容错；LLM 输出经 `robust_json` 解析后 score 若为带单位字符串（如 "9分"）或数组，`float()` 抛 ValueError/TypeError，异常从 `_run_track` 传播到 `daily()` 的 except，整次运行标记 failed（尽管只是读者审稿一个字段的格式问题，且该链路其余部分正常）。项目其它地方（robust_json、parse_guard 等）均做容错，建议对这两个字段用 try/float 兜底。

- [P3] merge_blueprints 对非数字 seq 抛 ValueError，周会决定整体不落盘 — E:\code\novel-editorial\tools\apply_architect.py:18-23
  apply_architect.py:18-21 中 `int(b.get("seq") or 0)` 对 LLM 报告里非数字的 seq（如 "next"、"第3章"）直接抛 ValueError，异常沿 `apply_report` 传播到 meeting_session 的调用处（有 try/except 兜底，记录 `apply_report_failed` 后跳过），导致该次周会的 blueprints/reader_persona/finish_decision 等全部决定不落库。后果有 audit 可见、非静默，但建议对 seq 做 `re.match(r'\d+')` 提取或 try/int 容错，避免一次字段异常丢弃整份会议决定。

- [P3] meeting_actions 幂等标记先于副作用提交，副作用失败后永久不可重试 — E:\code\novel-editorial\tools\meeting_actions.py:51-53
  meeting_actions.py:37-53 先 INSERT 幂等 marker 并 `conn.commit()`，再执行 `_insert_draft`/audit 等副作用；若副作用阶段抛异常（如 SQLite 写锁超时），marker 已落库，重跑 `run_post_actions` 会命中 `marker.rowcount == 0` 返回 skipped，该次会议的知识草案/审阅记录永久丢失且无提示。docs/reviews/20260812-0330-slice-editorial.md 已将该模式标记为需修复的回归；建议改为先执行副作用、最后写 marker 并提交（或失败时删除 marker 回滚）。
