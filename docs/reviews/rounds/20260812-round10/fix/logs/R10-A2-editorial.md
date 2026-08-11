修完了mashitawa。按项说给你听，全程只动了分配给我的四个文件，其他工作区的并行改动我一根手指都没碰desuwa。

R10-A2-01，workday.py 274-296。close 之前无条件再写一遍 daily 日记，和 open 里 daily() 收尾链的「全员写日记」重复，日记、cost_logs、activity 全翻倍。现在 close 先按 novel_id + diary_type='daily' + created_at>=started_at 查一遍，produce 日已经写过就跳过并留 `diaries_skipped` 审计痕，org/meeting 这类非产出日没有日记才补写desuwa。实测 open+close 后日记数从 22 回到 11，没双写mashitawa。

R10-A2-02，editorial_daily.py 1282、1298-1336。`_settle_rework` 原来无条件把行动项标 done，重试链全挂也假成功。现在调用处把最终 gate 的 passed 传进去，失败时行动项保持 pending、result 写明「未通过质量门，等待人工跟进」，另写一条 `settle_rework_failed` 审计留痕；只有真正过稿才标 done。成功路径的既有测试原样通过desuwa。

R10-A2-03，editorial_daily.py 207-214。`_handle_agency` 弹出 agency 后把剩余对象整个 JSON 化，散文 Agent 返回 `{"text": 正文, "agency": [...]}` 时正文就被信封污染。现在和 `_handle_outbox` 一致，只剩 text 字段时直接解出纯正文，纯文本和普通 JSON 结构都不受影响mashitawa。

R10-A2-04，agent_meeting.py 660-678、727-772、771、790-825、858-866。dry-run 下发言的 `meeting_speech`/`meeting_speech_failed` activity、`meeting_summary`、topic 会议日记、`generate_post_meeting_actions`、`apply_report`/`create_planning_from_next_book` 全部闸掉，异常分支的 activity 也门控了。session 和 weekly_meetings 归档保留——第九轮审查明确写了这是「有意」行为，既有测试也锁着它，我按这个边界修desuwa。整链 CLI 实测：dry-run 后 agent_actions=0、agent_activity=0、agent_diaries=0，novels 不被重写，只剩有意的两行归档。

R10-A2-05，architect_weekly.py 68。`_safe_int` 对 None 和空串直接静默回默认值，不再对缺省设置库刷三条 stderr 告警；真异常像 "abc" 仍照旧告警。我用 redirect_stderr 验证过：None/空串零输出，"abc" 有 note 输出desuwa。

R10-A2-06，agent_meeting.py 543-554、563、697。我选了补生成链而不是删死读取，理由有三：`_meeting_directives` 已经接进日更上下文注入（editorial_daily.py 1510 附近），webapp 的 MeetingsPage 也显示这个徽标，删了等于砍掉整个功能；而 agent_meeting.py 本来就在本轮可改名单里。现在 chair_summary 的报告格式和 dry-run mock 都带上 `writing_directives` 字段，main() 里 setdefault 兜底，会议报告从此真的会产指令，`_meeting_directives` 不再是空转desuwa。

R10-A2-07，editorial_daily.py 568-571。`_preflight` 算出 ok=False 时（含锁失败）把 "preflight" 追加进 ctx.failed_nodes，`_finish_run` 会把它写进 daily_runs.failed_nodes，flow_graph 的 FAILED_ALIAS 本来就有 preflight 映射，链路图能直接高亮预检节点了。我用预算为 0 的库实测，failed_nodes 里确实带 "preflight"desuwa。

验证：`python -m compileall` 四个文件全过，workday 单独 py_compile 也过；相关测试挑了两轮跑，218 项全绿，包括 test_meeting_dry_run_full_chain、test_run_track_instant_rework_closes_loop、test_handle_agency 系列和 test_meeting_directives_injected。七个修复点各写了针对性功能脚本，全部通过mashitawa。

额外发现，只报不改：一是 resume 路径还有同源风险——重复 resume 会再触发 daily() 的收尾链再写一轮日记，close 的去重挡得住 close 那次，挡不住 resume 自身；二是 `docs/tmp_fix/R10-*.err` 一堆像是历次修复任务的错误日志留在仓库 docs 里，看着像该归档的杂物；三是 agent_meeting dry-run 仍会写 n8n_tmp 的归档 JSON（我验证时生成了一个，gitignored 且删除被策略拦了，就留在那儿）。另外 preflight 的 skipped 分支不算失败所以不进 failed_nodes，如果你想让「日更暂停」也高亮，可以单独开项desuwa。

MEMORY.md 没有更新——它不在本轮允许修改的文件清单里，我只动了指派的那四个teyo。
