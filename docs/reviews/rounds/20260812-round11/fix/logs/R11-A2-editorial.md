弄好了mashitawa。八项里七项落了刀，第七项查完发现是误报——一个字都没改desuwa。

R11-A2-01（editorial_daily.py:1161-1172）——`_review_retry` 重试耗尽且原始 gate 已通过时，现在返回 failed gate（passed=False + 失败原因），正文保留原始通过稿而不是最后那次失败重写稿，`_settle_rework` 随之按 pending 结算。探针确认 gate 不再通过、原文保留、errors 非空，test_review_retry 全绿。

R11-A2-02（workday.py:157）——open 的活跃守卫从 `status='running'` 改成 `phase!='finished'`，org/meeting 的 skipped+awaiting_close 行同样拦住并发开日。插入 org 待收工行后第二次 open 确实被拒，报「尚未收工」。

R11-A2-03（workday.py:64-93, 154）——新增 `_recover_stale_open`，参照 daily_runs 的 12 小时阈值回收卡在 opening/morning/producing/closing 的孤立行，标记 failed+finished 并留审计；awaiting_close 是刻意决策点，不回收。13 小时前的 opening 行实测被回收，open 正常继续。

R11-A2-04（editorial_daily.py:218-237）——`_mark_injected_read` 改为和 agent_context 完全一致的作用域（`ref_novel_id IN (0, 当前书)`），novel_id=0 的全局消息注入后也会标读。实测全局和业务消息都变成了 read。

R11-A2-05（export_flow_html.py:73, 83）——`completed_with_pending` 映射为「上次完成（有待办）」加 warn 样式。渲染 HTML 里新文案和 `status warn` 都在desuwa。

R11-A2-06（agent_meeting.py:619, 647）——CLI 的 `chair_pick` 和 `round_speech` 都补传 `kind=args.kind`。dry-run topic 会议实测提示词带「剧情碰头会」「主题观察」，周会议程标签不再出现在议程位。

R11-A2-07（agent_meeting.py:280）——不改。`compress_history` 根本不是死代码，`novel_editorial/services/meeting_session.py:484` 的交互式会议链路一直在调它，审查只在 tools/ 里搜所以误判了mashitawa。

R11-A2-08（workday.py:54-61, 267, 322 + editorial_daily.py:1473-1487, 1706, 1810-1813）——resume 触发收尾链前先查日记是否已存在，存在就传 `skip_diaries=True`，`_wrapup` 跳过全员写日记并留 `diaries_skipped` 审计；close 的去重抽成同一个 helper 复用。实测有日记时 skip=True 且零写入，无日记时正常写。

验证汇总：`python -m compileall` 四个文件全过；pytest 跑了 9 个相关测试文件共 104 项，全绿（74 + 30）。工作区里其他文件的改动是并行任务包留下的，我没碰；MEMORY.md 不在允许清单里，没动desuwa。

测试建议（不改测试文件）：test_review_retry 补一个「原始 passed gate + 重试全失败」用例——现有 mock 让原文和重写文本长得一样，正好抓不住这个洞；test_workday 补 org 行二次 open 拦截、stale opening 回收、resume 日记去重三例；再补全局消息标读和 CLI kind 透传的断言。

额外发现，只报告不改：一是 `daily_runs.local_executions` 和 `flow_graph` 也没映射 completed_with_pending，面板执行列表会露原始状态，但这两个文件不在本轮指派范围；二是 `mailroom.list_messages` 的 novel_id=0 语义是「不过滤」而非「只看全局」，这恰是原来标读漏掉全局消息的根源，API 层这个坑建议以后单独修；三是 agent_meeting dry-run 的 mock 发言文本里仍写「本周小结」，topic 会议预览会出现这个词，纯 cosmetic；四是 close/resume 对 opening/morning 阶段依旧拒绝，孤立行恢复只发生在下次 open()，12 小时内想直接 close 还是会报错，这是当前设计的边界，先跟您说一声desuwa。
