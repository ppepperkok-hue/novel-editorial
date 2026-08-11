六项都修完验证过了mashitawa。汇报如下。

R6-B-01（P1）：[tools/relations.py](/E:/code/novel-editorial/tools/relations.py:33) 的 `ensure` 现在先读 `PRAGMA table_info` 动态选列，旧迁移库走 `other_agent`（NOT NULL 的那个），新库走 `other`；旧库插入时两个列都写，保证迁移后的 `other` 也同步。SELECT/INSERT 全程包了异常，schema 读不到或写不进就返回错误 dict，不再让日更整个炸掉。我用工作区真实的 demo.db（正是旧结构，实测复现了 `NOT NULL constraint failed: agent_relations.other_agent`）验证：ensure 建行成功，apply_event 也正常落库desuwa。

R6-B-02（P2）：[tools/editorial_daily.py](/E:/code/novel-editorial/tools/editorial_daily.py:79) 加了 `_outbox_int`，`reply_to`（112 行）和同函数里同样裸 `int()` 的 `chapter_id`（121 行）都走容错转换，非数字按 0 处理并进 `ctx.warnings` 留痕。顺带说一句，`chapter_id` 是同一行簇里同类的崩溃点，一并修了，不然只修 reply_to 还是会被非数字 chapter_id 拖垮mashitawa。

R6-B-03（P2）：[tools/editorial_daily.py](/E:/code/novel-editorial/tools/editorial_daily.py:1677) 的 skipped 分支拆成两条路——workday 来源的行调用 `_finish_run` 标记 `status='skipped'`、error 写清原因、detail 带 reasons，保留给面板看；自建的调度行才 `DELETE ... WHERE run_id=? AND source='scheduler'`。复现脚本确认 workday 行不再被删，状态正确变成 skippeddesuwa。

R6-B-04（P3）：[tools/daily_runs.py](/E:/code/novel-editorial/tools/daily_runs.py:98) 的 `sync_from_n8n` 把 n8n 本地库读取和同步循环都包进异常防护，损坏库返回 `{"written": 0, "error": "n8n 本地库读取失败：DatabaseError"}`，不 500；中途失败也会提交已写部分并带错误标记。`_n8n_executions` 的返回契约保持列表不变，`tests/test_web_api.py` 里 mock 空列表的用法不会破mashitawa。

R6-B-05（P3）：[tools/agent_meeting.py](/E:/code/novel-editorial/tools/agent_meeting.py:749) 的 `apply_report` 调用现在对 `ImportError` 和其余异常分开捕获，outline/report 损坏时打印 note 并写一条 `meeting_apply_skipped` 活动记录，会议 CLI 正常收尾。用 outline 写成 `not-json{` 的库实测：之前 exit 1 崩在 `json.loads`，现在 exit 0、会议产物照常归档desuwa。

R6-B-06（P3）：[tools/editorial_state.py](/E:/code/novel-editorial/tools/editorial_state.py:10) 确认 `(0,)` 分支不可达——三个调用点都先 `if novel_id:` 守卫，删掉死分支，统一返回 `(0, novel_id)`，行为不变desuno。

验证：`python -m compileall` 五个文件全过；相关测试（relations、db、outbox、editorial_daily、daily_runs、editorial_state、agent_meeting、web_api）99 个全绿，全量 pytest 485 个也全部通过。只动了指派的那五个文件，没碰 MEMORY.md，也没 git add/commitdesuwa。

额外发现，只报告不改：`tools/workday.py` 的 produce 路径在 `daily()` 返回 skipped 后本身不标记状态，之前靠 daily 删行掩盖了，这次在 daily 里直接标 skipped 后 workday 路径闭环，无需再动；`_review_tone` 等日更内部查询仍硬编码 `other=?`，对没被迁移回填 `other` 的旧数据会漏匹配，属于迁移层遗留，不在本包范围；仓库里还有 `docs/tmp_fix/R6-B-editorial.err` 这个未跟踪的上次会话日志，按纪律我没清理，建议之后归档或删掉desuwa。
