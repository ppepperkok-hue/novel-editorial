# 多 Agent 协作部分评估报告（2026-08-10）

> 状态：2026-08-10 已按本报告完成全部 P1/P2 与阶段四改造（见文末
> 「实施记录」），本报告保留原始问题清单作为设计依据。

审查方式：逐文件阅读 `prompts/agents/*.md`、`tools/agent_meeting.py`、
`novel_pipeline/services/meeting_session.py`、`activity.py`、`knowledge.py`、
`tools/agent_tool_loop.py`、`write_diaries.py`、`architect_weekly.py`、
`distill_lessons.py`、`knowledge_keeper.py`、`get_meta.py`、`record_work.py`、
三个 n8n 工作流 JSON 与前端 `MeetingLive/MeetingsPage/AgentsPage`。

## 结论摘要

协作骨架已经立起来：会议-日记-行动项-活动日志-知识工具调用五件套齐备，
周会/专题会议可以"开会 → 领任务 → 回填结果"，面板能看到会议发言、日记和行动项。

但协作目前只在会议层闭环，存在三个结构性缺口：

1. **会后任务进不了日更执行链路**：行动项只注入周会材料（`agent_briefs.my_pending_actions`），
   日更的写手/守护/审稿任务文本里完全没有待办引用，会议结论对每天写章零影响。
2. **日更主链路零活动日志**：`agent_tool_loop`、`get_meta`、`record_work`、
   `knowledge_keeper`、`distill_lessons` 都不写 `agent_activity`。面板能回答
   "谁开会说了什么"，回答不了"写手今天写了什么、审稿拦了什么"。
3. **两条 LLM 调用路径行为不一致**：`/api/agent/run` 代理口有 3 次重试 +
   无工具降级；会议引擎一次失败即整场失败/占位，无重试无超时熔断。

其余问题集中在上下文单薄、知识匹配过宽、model 参数失效等，见下。

## P1（重要，建议优先）

### 1.1 行动项不进日更链路

证据：`n8n/novel_workflow.json` 全部 15 个 `/api/agent/run` 节点的 `task` 中
没有 action/pending 引用（脚本扫描 `has_action_ref=False`）；`agent_tool_loop.run`
只拼接 `prompts/agents/*.md` + 任务文本 + 知识索引，不读 `agent_actions`。

影响：周会"建立伏笔台账"这类结论只在下一次会议被想起，写正文时没人执行；
行动项变成仪式性产出。

建议：
- `web_api /api/agent/run` 收到请求后查询该 agent 的 pending actions，
  在 task 后追加「我的待办：…（完成请在结果中回填）」；或
- 在 `get_meta` 输出的 writing_context 中注入待办（改动更大，涉及 n8n jsCode）。

验证：跑一次日更，写手/守护的任务文本含待办；完成后 actions 可被标 done。

### 1.2 日更主链路零活动日志

证据：对 `agent_tool_loop.py / get_meta.py / record_work.py / knowledge_keeper.py /
distill_lessons.py` 全文检索 `activity` 均无命中。

影响：用户问"每个 agent 今天干了什么"，日更的 Planner/写手/润色/审稿/主编/守护/
读者审稿全部不可见；活动日志只有会议与日记两类来源。

建议：
- `agent_tool_loop.run` 成功与失败都写 `agent_activity`：
  `activity_type` 用 `chapter`（写手/润色）、`plan`（Planner）、`review`（审稿/读者/主编）、
  `guard`（守护）、`summary`（提炼剧情）；
- `record_work.py` 收尾补一条 `system` 级活动（本日生成/发布汇总）；
- `knowledge_keeper.py` 与 `distill_lessons.py` 补 `knowledge` 类型活动。

验证：日更后 `/api/activity` 出现各 agent 的 chapter/review 记录。

### 1.3 会议引擎无重试与超时熔断

证据：`agent_meeting.ask()` 单次 `chat_deepseek`，异常直接上抛；
`meeting_session._run_locked` 中 `chair_pick / chair_summary / compress_history`
任一步异常即整场会议标 failed；`round_speech` 失败仅占位不重试；
`_run_locked` 无整体超时，只有前端心跳提示（>300 秒）。

影响：一次瞬时网络错误就让整场会报废；agent 卡死时会议线程永久占用。

建议：
- `ask()` 增加 2-3 次退避重试（对齐 `agent_tool_loop` 的重试策略）；
- `round_speech` 失败后重试 1 次再占位；
- `_run_locked` 增加整体超时（如 60 分钟）与心跳更新，超时标记 failed 并审计。

### 1.4 行动项生成不读 agent 人格

证据：`activity.generate_post_meeting_actions` 的 system 是固定文本
"你是会议行动项整理器"，不读 `prompts/agents/{agent}.md`，不知道角色职责。

影响：任务可能与职责错位（比如给 memory 生成"写正文"类任务）。

建议：注入该 agent 人格文件的职责/关注点段落（或 `AGENT_DISPLAY` 描述）作为 system。

## P2（改进）

### 2.1 代理口 model 参数被忽略

证据：n8n 请求体显式传 `model:'deepseek-v4-pro'`，但 `web_api /api/agent/run`
不把 model 传给 `agent_tool_loop.run`，实际模型来自 md frontmatter。
当前两者恰好一致，但 n8n 里改模型不会生效，误导维护。

建议：web_api 接受 `payload.model` 覆盖；或从 n8n 请求体删除 model 字段统一由 md 决定。

### 2.2 知识工具匹配过宽

证据：`knowledge.resolve_knowledge` 中 `if not topic or topic in hay or any(...)`：
topic 为空时返回该 agent 全部知识包；子串匹配会误配（如 topic=“点”命中“爽点”包）。

建议：空 topic 返回空并提示；匹配改为关键词/标题 token 重合度，命中数上限 3。

### 2.3 n8n 定时周会不可回放完整对话

证据：`agent_meeting.py main()` 落 `weekly_meetings` 时 `session_id=0`，
transcript 只写 `n8n_tmp/meeting_*.json`；前端"查看完整对话"对 session_id=0 无内容。

建议：`main()` 也创建 `meeting_sessions`（kind=weekly）并在结束时写入
transcript/report，或给 `weekly_meetings` 增加 transcript 列。

### 2.4 润色/审稿上下文单薄

证据：润色任务只有初稿文本（n8n jsonBody 292 字符）；审稿任务无章纲意图
（hook/emotion），无法按"作者意图"评分。

建议：润色注入 bible 摘要（角色+文风+禁止词）；审稿注入本章 outline/hook/emotion。

## P3（可选）

- `agent_md` 每次读文件无缓存（影响小）；
- `/api/agent/run` 本机无鉴权（信任模型，README 已声明）；
- 会议 transcript 前端全量轮询，20 轮以上会变慢（可做分页/增量）；
- 前端活动日志 detail 目前只展示 speech/what_done/task 三类，日更接入后
  需要 chapter/review 类型的摘要展示。

## 分阶段改进路线

### 阶段一：协作闭环（1-2 天）
行动项注入日更 + `agent_tool_loop` 活动日志。
验证：跑一次日更，任务文本含待办；`/api/activity` 出现 chapter/review 记录；
前端 Agent 管理页能看到写手今日产出摘要。

### 阶段二：会议健壮性（1 天）
`ask()` 重试、`round_speech` 失败重试 1 次、会议整体超时熔断、
行动项生成读人格。
验证：mock LLM 失败，会议仍完成且留痕；dry-run 全链通过。

### 阶段三：上下文与知识精度（1 天）
润色/审稿注入 bible 摘要与章纲意图；知识匹配收紧；代理口 model 统一。
验证：dry-run 检查任务文本；知识检索命中率抽查。

### 阶段四：可观测完善（半天）
n8n 周会 transcript 落库回放；前端活动详情按类型展示。
验证：周会档案页可回放完整对话；活动时间线含全部 agent 类型。

## 实施记录（2026-08-10）

- **P1-1 行动项进日更**：`web_api /api/agent/run` 自动查询该 agent 的
  pending actions 并追加到任务文本（按 novel_id 过滤，失败不阻塞）。
- **P1-2 活动日志**：`agent_tool_loop.run` 成功/失败都写
  `agent_activity`（plan/chapter/review/guard/summary/meta/ending/knowledge）；
  `record_work` 写 daily_summary；`knowledge_keeper` 写 knowledge；
  `distill_lessons` 写 distill。
- **P1-3 会议健壮性**：`agent_meeting.ask` 三次退避重试；
  `meeting_session` 增加 60 分钟硬超时熔断（含主席点将前检查）。
- **P1-4 行动项生成读人格**：`generate_post_meeting_actions` 注入
  `prompts/agents/{agent}.md` 前 800 字符作为派活依据。
- **P2-1 model 统一**：web_api 透传 `payload.model`，agent_tool_loop 支持
  model 覆盖，n8n 请求体与人格 frontmatter 不再各自为政。
- **P2-2 知识匹配收紧**：空 topic 不再返回全部包；关键词双向匹配要求
  词长 ≥2；命中上限 3。
- **P2-4 润色上下文**：润色 A/B 任务注入角色卡、人物关系、世界观规则与
  文风指南（渲染工作流后仍保留，深度校验通过）。
- **P2-3 周会回放**：`agent_meeting.py main()` 创建可回放的
  `meeting_sessions`（kind=weekly），结束写入 transcript/report 并关联
  `weekly_meetings.session_id`。
- 前端 Agent 管理页活动日志新增全部活动类型标签与
  output/error/published 详情展示。
- 验证：159 后端测试 + 6 前端测试全绿，工作流深度校验通过，
  前端构建通过，全量测试后 demo.db/n8n/alerts/queue 零污染。
