# Multi-Agent Coordination Design (2026-08-10)

## 参考项目与启发

| 项目 | 核心做法 | 对我们的启发 |
| --- | --- | --- |
| [CrewAI](https://github.com/crewAIInc/crewAI) | crew/task/agent 全生命周期事件，可观测中间决策 | 每个 agent 的工作都应有事件记录，而不是只看最终产物 |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | Role 记忆系统，长时记忆随启动恢复/变化更新 | 记忆要跨会话连续，周会前必须回放本周工作 |
| [OWWZO/ai-agent](https://github.com/OWWZO/ai-agent) | 执行事实记录 + 历史回放（LLM 调用、工具调用、输出、文件产物） | 面板需要能按 agent、按天回看"干了什么" |
| [Morpheus](https://github.com/papysans/Morpheus) | 多智能体长篇小说创作，L1/L2/L3 三层记忆，轨迹与指标子系统，上下文装配与回写 | 记忆分层 + 轨迹子系统与我们的小说知识库互补 |
| [Novel-OS](https://github.com/mrigankad/Novel-OS) | 持久故事状态 story_state.json，五角色编辑流水线，确定性连续性引擎先于 LLM Guardian | 每个 agent 输出结构化更新块并解析回写；连续性检查先做确定性规则，再上 LLM |
| [AgentWeave](https://github.com/arniesaha/agentweave) | OpenTelemetry 追踪决策、成本、委托链 | 成本与委托链应随活动日志一起可查 |
| [agent-observability-kit](https://github.com/itskai-dev/agent-observability-kit) | 跨框架统一观测面板，<1% 开销 | 观测是基础设施，不是事后补丁 |

## 本次落地的机制

### 1. agent_activity：活动日志（谁、何时、干了什么）

每次 agent 实际工作都写入一条活动记录：

- `meeting_speech`：会议中每轮发言（含发言摘要、提案）
- `meeting_summary`：主席总结（含结论、行动项数量）
- `diary`：每日日记 / 每周周记写入
- `action_created` / `action_done` / `action_status`：行动项生命周期
- `knowledge`：知识管家维护
- `system`：流水线级事件（预留）

面板按天分组展示，可按 agent 过滤，回答"每个 agent 今天干了什么"。

### 2. agent_actions：会后任务

会议结束后，每位参会 agent 基于会议结论 + 自己的发言生成 1-3 条会后任务：

- LLM（flash）按人格/职责产出 `{task, reason, expected_output, due}`
- LLM 失败或报告截断时规则降级：按 owner 匹配报告 action_items，仍无则生成"复盘落实"任务
- 状态机：pending → done / skipped，完成时记录 result 与时间
- 每周材料构建时注入 `my_pending_actions`，agent 参会/写周记时看到自己的待办，形成"会议结论 → 执行 → 下次会议汇报"闭环

### 3. 完整会议日志回放

- 交互式会议的 `meeting_sessions.transcript` 保留逐轮逐人发言
- `weekly_meetings.session_id` 关联回放源，面板"查看完整对话"按轮次渲染
- 周会报告 JSON 只作摘要，完整对话永远可回溯

## 与现有系统的关系

- `agent_diaries` 是记忆（agent 自己的视角），`agent_activity` 是事实（系统视角），两者互补
- `agent_actions` 是决策闭环的执行层，周会材料注入待办后，会议不再是"议而不行"
- `novel_knowledge` 是书内设定事实库，`prompts/knowledge/*` 是写作技巧库；活动日志记录谁用了什么知识，便于后续做知识效果归因

## 后续演进（未实现）

- 工具调用级日志：`agent_tool_loop` 的每次 tool_calls/检索结果落 activity（当前只记录会议发言里的工具使用摘要）
- 日更节点级日志：`record_work.py` 聚合 n8n 各节点输出后，按 agent 落 activity
- 委托链/成本关联：activity 挂 run_id，与 cost_logs 关联
- 行动项到期提醒：due 过期未完成时进入面板告警

