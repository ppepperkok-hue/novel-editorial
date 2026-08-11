修完了mashitawa。八个修复项全部落地，四个指派文件之外一个字没碰desuwa。逐项给你对账teyo：

| 编号 | 文件:行号 | 改动摘要 | 验证 |
| --- | --- | --- | --- |
| R7-B2-01 | agent_meeting.py:580-615、778-795 | planning 不再解析 novel-id/book-id、不取最新书，直接用 `build_planning_materials`；落盘改走 `create_planning_from_next_book`，不再 `apply_report` 改写已有书 | 用已有 publishing 书跑 planning dry-run：session novel_id=0，书 outline/cover_prompt/status 原样未动 |
| R7-B2-02 | agent_meeting.py:642-671、833-856 | 轮次内 per-agent try/except，失败写占位发言并记 `meeting_speech_failed` 活动，会议继续；外层异常把 running 会话标 failed | 注入发言异常：transcript 含失败占位、活动 1 条、会话 finished；注入 chair_summary 异常：会话 failed |
| R7-B2-03 | export_flow_html.py:54、74、83、112、125、195 | skipped 映射「已跳过」+ 独立紫色 skip 样式，节点/边/图例同步 | skipped 运行渲染出「已跳过」与 `status skip` |
| R7-B2-04 | flow_graph.py:23、68-69、125-127 | 新增 dispatch 节点（主编分派）及 stock→dispatch→planner 边；FAILED_ALIAS 增加 eic/主编分派/分派 | `["eic","主编分派","分派"]` 均映射为 failed_ids=["dispatch"] |
| R7-B2-05 | agent_meeting.py:229-232 | 删除 ask 内重复的 knowledge import，用顶层引用 | 编译与测试通过 |
| R7-B2-06 | meeting_actions.py:11-13 | 删除 config/audit 死导入 | 编译与测试通过 |
| R7-B2-07 | meeting_actions.py:78-101、119-123 | review/critique 审计改为直插 SQL，与幂等标记同一事务提交；失败 rollback 后重试不重复 | review/critique 各重跑一次审计行仍为 1；中途失败后草稿与标记为 0，重试成功且无重复 |
| R7-B2-08 | export_flow_html.py:147-148 | JS 端加 STATUS_MAP 白名单，未知状态回落 idle | 抽取 JS 用 node --check 通过；未知状态渲染为 `class="status idle"` |

验证上，`python -m compileall` 四个文件全过，33 项切片测试和 82 项关联会议测试全绿，HTML 内嵌 JS 语法也验过了mashitawa。

额外的发现只报不改desuwa。一是交互式 planning 路径的根因在 `novel_editorial/services/meeting_session.py`（create_session 仍把 planning 绑最新书、_run_locked 对非 0 novel_id 仍调 apply_report），该文件不在本次指派范围，建议下一轮处理。二是 `run_post_actions` 的幂等是「先查后插」，同进程重试已安全，但并发双跑理论上会同时通过检查，要彻底得靠唯一索引。三是整轮失败时链路图会给所有节点上 bad/failed 样式而不是只标失败节点，这是既有展示口径，没动它。

仓库的 MEMORY.md 我没有更新，工作区里其他文件的改动也都原样保留mashitawa。
