228 个针对性测试与 dry-run 端到端均通过，核心链路（日更调度、质量门、会议、邮件、承诺/关系）契约正确；但 workday 的 close/resume 在 dry-run 下仍真实写入状态机（已复现破坏性副作用），属于必须修复的功能缺陷，因此整体判定为不正确。其余为 P3 级健壮性与一致性问题，不阻塞发布但建议后续清理。

Full review comments:

- [P2] dry-run 收工/续工仍写入状态机，会真实关闭工作日或阻塞后续 open — E:/code/novel-editorial/tools/workday.py:306-309
  workday.close(dry_run=True) 与 workday.resume(dry_run=True) 未保护状态机写入：`_close_locked` 中 `_update(conn, run_id, status=final_status, phase="finished", legacy=...)`（tools/workday.py:306-309）及 `phase="closing"`（:248）、collab_summary（:264）、audit（:310-314）都在 dry_run 分支外执行，dry_run 只跳过日记/广播；resume 的 `_update(conn, run_id, phase="producing", status="running")`（:213）同样无条件执行。已复现：对 phase=awaiting_close 的 run 执行 `close(dry_run=True)` 后 status 变为 `failed`、phase 变为 `finished`，run 被真实终结；对 status=skipped 的 run 执行 `resume(dry_run=True)` 后 status 变为 `running`，随后 `open()` 返回“上一个工作日尚未收工”被阻塞。CLI `--dry-run` 预览或任何调用方误用都会产生破坏性副作用。

- [P3] flow 报告把 daily_runs.status 未转义插入 HTML class 属性 — E:/code/novel-editorial/tools/export_flow_html.py:125-125
  tools/export_flow_html.py:125 `<span class="status {status}">{status_text}</span>` 中 status 直接来自 `last_run.status`，未做 html.escape（同函数中 summary/error 都转义了）。已复现：status='x" onmouseover="alert(1)' 时输出 `<span class="status x" onmouseover="alert(1)">`，可注入任意属性。status 可由 daily_runs.sync_from_n8n 从外部 n8n 本地库写入（tools/daily_runs.py:69），本地报告场景风险有限，但与其余字段的转义策略不一致。

- [P3] export_flow_html 中 groups 变量为死代码 — E:/code/novel-editorial/tools/export_flow_html.py:81-83
  tools/export_flow_html.py:81-83 计算 `groups = "".join(f'<span class="chip">{GROUP_LABEL[g]}</span>' for g in GROUP_X)` 后从未使用，属于无用计算（GROUP_X 是 dict，迭代 keys 的顺序也不可依赖）。应删除或实际渲染到模板。

- [P3] rework_applied 全局标志导致第二个重做请求被静默丢弃且行动项悬置 — E:/code/novel-editorial/tools/editorial_daily.py:1160-1167
  tools/editorial_daily.py:1160-1167 中 `ctx.rework_applied` 是全局标志：track A 处理任意 rework 请求后置 True，track B 即使存在 `ctx.rework_requests[1]` 也会走 elif 分支，`_settle_rework` 只结算了 track A 的请求，track B 对应 action 永远停留在 pending（`_settle_claimed_tasks` 只处理 writer 的 action，rework action 的 agent 是留言方）。当审稿人与读者同时留言重做时，第二个重做意图丢失。

- [P3] relations.decay 的 days 参数从未使用 — E:/code/novel-editorial/tools/relations.py:85-88
  tools/relations.py:85-88 `def decay(conn, novel_id=0, days=7)` 接收 days 但衰减幅度固定（familiarity/trust ×0.95、friction ×0.90），与注释“weekly decay”的周期间接绑定在调用频率上；write_diaries 每周结算一次尚可，但任何调用方提高 settle_promises 频率都会使关系值按调用次数加速衰减到 0，days 形同虚设，建议要么实现按 days 计算衰减，要么移除参数。

- [P3] meeting_actions 幂等标记检查与插入非原子，并发可重复应用 — E:/code/novel-editorial/tools/meeting_actions.py:33-38
  tools/meeting_actions.py:33-38 先 SELECT audit_logs 检查 post_actions_applied 标记，随后插入 knowledge_drafts 并在最后才写标记 + commit，检查与写入之间没有事务/唯一约束。两个连接并发调用 run_post_actions 时都可越过检查，重复插入 incident/retro/learning 草稿（第二个连接在第一个 commit 后继续执行其已排队的 INSERT）。建议把标记写入与草稿插入放进同一事务或对 drafts 加唯一约束。

- [P3] 发布链 cover_article 响应未检查，失败静默继续发布 — E:/code/novel-editorial/tools/editorial_daily.py:1245-1245
  tools/editorial_daily.py:1245 对 `_fanqie_post(... /article/cover_article/v0/ ...)` 的返回值直接丢弃，未检查 code 是否非 0。若番茄侧存稿内容写入失败（返回错误码而非异常），流程仍继续 publish_article，最终要么发布空/旧内容，要么在 publish 步骤才暴露错误，中间失败无任何日志痕迹。与 new_article/publish_article 的显式错误处理不一致。

- [P3] 主编分派与重写轮中的 mailroom 调用未检查返回值 — E:/code/novel-editorial/tools/editorial_daily.py:621-626
  tools/editorial_daily.py:621 `mailroom.broadcast(conn, "eic", ...)` 与 :1012 `mailroom.send(...)`（_review_retry 内）的返回值均被忽略，mailroom.send 失败（如空 body、非法 agent）时不会进入 ctx.warnings/errors，run 仍可能以 completed 收尾，与模块 docstring“failures are never silent”及代码库其他位置的显式警告风格不一致。

- [P3] agent_meeting.ask 工具循环 final round 无重试，单次网络抖动会中断整场会议 — E:/code/novel-editorial/tools/agent_meeting.py:252-263
  tools/agent_meeting.py:252-263 中工具调用后的 final round 直接调用 `chat_deepseek(...)`，无重试也无空响应兜底（对比同文件 :196-208 首轮有 3 次重试、agent_tool_loop.py:388-399 final round 有 3 次重试）。final round 抛异常或返回空 content 时异常冒泡到 main()/meeting_session 调用方，已生成的多轮发言记录不会归档到 weekly_meetings。建议与 agent_tool_loop 对齐加重试。

- [P3] 周会材料/落盘对 novels.outline 的 JSON 解析无异常保护 — E:/code/novel-editorial/tools/architect_weekly.py:181-181
  tools/architect_weekly.py:181 与 tools/apply_architect.py:188、:343 直接 `json.loads(row["outline"] or "{}")`，若 outline 列被外部工具或手工编辑写坏（非 JSON），build_materials/apply_report 会抛 ValueError 中断整场会议落盘；其余 DB 字符串字段（tags/attendees/report 等）都有容错解析。建议统一用 try/except 降级为空 dict。
