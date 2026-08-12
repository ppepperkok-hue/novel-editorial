# 会议系统改造：hermes 模式评估与工程表（2026-08-12）

## 1. 背景与目标

用户提供参考项目 [hermes-studio](https://github.com/EKKOLearnAI/hermes-studio)（多平台 AI 聊天 + 群聊房间系统），要求评估「全盘移植其会议模式」的可行性，并按工程 skill 产出评估报告与工程表。

**目标**：让编辑部会议从「固定轮次串行广播」进化为「实时群聊式自由讨论」——老板可实时围观、@指定编辑、拍板审批；长会议不崩；不破坏现有周会/留痕/报告体系。

**参考结论（详见第 4 节）**：不引入 Node/Socket.IO/Vue 双栈；以 hermes 为「交互规格 + 算法参考」，在现有 Python + React 栈上分阶段实现「会议房间子集」：自由讨论模式、@提及路由、审批/澄清、SSE 实时推送、上下文压缩。

## 2. 参考系统能力清单（hermes group-chat）

证据：`packages/server/src/services/hermes/group-chat/index.ts`（4230 行 Socket.IO 服务）、`agent-clients.ts`（2467 行执行器桥）、`mention-routing.ts`（132 行 @路由）、`GroupChatPanel.vue`（4646 行前端面板）、`packages/server/src/index.ts`（Koa + Socket.IO 单进程）。

| 能力 | 实现要点 | 我们是否已有 |
| --- | --- | --- |
| 实时房间 | Socket.IO namespace，成员在线/typing/进出广播 | 无（前端 2.5s 轮询） |
| @提及路由 | 自然语言 @name/@all，中文标点边界，剥离路由 token，结构化 mentions | 无 |
| 执行器桥 | `GroupAgentExecutor` 接口：sendMessage/interrupt/respondApproval/respondClarify/replyToMention；@提及入队串行 drain，可并行回复多个被提及 agent | 无（agent 调用在 meeting_session/agent_meeting 内串行） |
| 审批/澄清 | approval.requested → owner 响应；clarify.requested → 管理员响应；pending 路由 + 超时过期 + 幂等 | 无（「待您决定」靠轮询草稿/工作日状态） |
| 转交链 | agent 间 @转交，handoff depth 限制，continuation 持久化状态机 | 无 |
| 上下文预算 | token 记账、maxHistoryTokens、tailMessageCount、自动摘要锚点（summaryEveryTurns/模型） | 部分（tools/agent_meeting.py:280 `compress_history` 有雏形） |
| 消息系统 | 结构化内容块（text/image/file）、tool_calls、reasoning、run_id、canonical ordering | 部分（meeting_sessions.transcript 为 JSON 数组内嵌，无独立消息表） |
| 房间工作区 | 房间 workspace + diff 跟踪 + 远程文件 | 不需要（产出落库：weekly_meetings/agent_actions） |
| 数据库 | better-sqlite3，gc_rooms/gc_room_agents/gc_messages + handoff 表 | 需新增会议消息/审批表 |

## 3. 现状锚点（我们的会议系统）

| 组件 | 位置 | 说明 |
| --- | --- | --- |
| 会话状态机 | novel_editorial/services/meeting_session.py:30 create_session / :139 advance_session / :157 cancel_session / :863 start_session_async | 固定轮次：点将 → 逐轮发言 → 总结；transcript 内嵌 JSON |
| 发言与主席 | tools/agent_meeting.py:311 chair_pick / :358 round_speech / :459 chair_direct / :523 chair_summary / :210 ask / :280 compress_history | 六段发言结构、周会材料、周记注入 |
| 数据表 | novel_editorial/db.py:187 meeting_sessions（transcript TEXT '[]'、current_round/current_agent/heartbeat_at）；:269 agent_messages（横向协作消息，含 reply_to/status/resolution） | 会议消息无独立表；agent_messages 可作横向消息底座 |
| SSE 底座 | novel_editorial/web_api.py:402 `/api/events`、:1121 `_sse` | 已有 text/event-stream 实现，可扩展会议事件流 |
| 前端 | webapp/src/pages/MeetingsPage.jsx（发起/直播轮询 2.5s/历史）；MeetingLive 已删除旧版 | 聊天室形态需重写 |
| 实时快照 | usePipelineStore.liveSnapshot（App.jsx 订阅 /api/events） | 壳层已接 SSE，页面未用 |

## 4. 三条路线对比与决策

| 路线 | 内容 | 工作量 | 风险 | 决策 |
| --- | --- | --- | --- | --- |
| A 全盘移植 | 引入 Node 服务跑 hermes 原码 + Vue 前端，Python 业务桥接 | 21–32 人日 | 双栈长期维护；执行器桥接浅则丢失人格化；与现有周会/留痕体系冲突 | 不采用 |
| B 栈内会议房间子集 | Python 加 SSE 实时 + @路由 + 自由讨论 + 审批 + 压缩；React 重写会议中心 | 12–18 人日（分阶段） | 可控；SSE 单向够用；不引入新语言运行时 | 采用 |
| C 单项渐进 | 先 @指定，再审批，再 SSE，最后自由讨论 | 6–10 人日 | 最稳，但形态割裂、周期长 | 作为 B 的阶段顺序 |

**决策：B，按 C 的顺序分阶段执行。** 理由：hermes 的代码是 TS/Vue，直接搬入 Python/React 项目几乎全部重写；真正可复用的是算法与交互规格；我们的核心资产（11 位人格 agent、周记记忆、知识工具、报告落盘）只有栈内方案才能完整保留。

## 5. 技术难点清单（按影响排序）

### 难点 1：执行器桥 —— 把 @提及路由到人格 agent（P0，最大工作量）
hermes 的 executor 接的是通用模型会话（hermes/ekko/codex/claude），我们要接的是 `agent_tool_loop` + 人格 prompt + 周记/记忆 + 知识工具 + 六段发言结构。
- **影响**：桥浅则「一群能聊天的模型」，丢失拟人化；桥深则要处理工具调用、记忆注入、成本记录、失败重试。
- **对策**：新写 `meeting_executor.py`，实现 `reply_to_mention(conn, session, agent, mention_msg)`：组装会议上下文（材料 + 历史 + 该 agent 周记/心情 + 被 @ 内容）→ 调 `agent_meeting.ask` 或 `agent_tool_loop` → 落会议消息表 → 广播事件。串行队列按房间持有，防止同 agent 并发。
- **验收**：dry-run 下 @一位/多位/@all 均正确路由；发言带六段结构；失败有显式留痕。

### 难点 2：自由讨论状态机（P0）
现有 `advance_session` 是固定轮次推进；自由讨论需要：发言按 @路由/自然顺序驱动、主席可随时总结、老板可随时插话、与固定轮次模式并存。
- **对策**：`meeting_sessions` 增加 `mode` 字段（`rounds` 保留现有逻辑 / `free` 新状态机）；free 模式下 `advance_session(instruction)` 语义改为「以指令或 @ 消息入队」；`finish` 仍走主席总结（chair_summary）与报告落盘。
- **验收**：两种模式切换不破坏旧会话；free 模式 dry-run 全链可跑。

### 难点 3：SSE 实时推送（P0）
自研 http.server 无 WebSocket；SSE 单向足够（会议直播是服务端推 transcript/状态/审批，上行继续用现有 POST）。
- **对策**：新增 `/api/meetings/events?session_id=`（复用 `_sse` 模式），事件类型：`message`（新发言）、`status`（思考中/待命）、`approval`（待审批）、`heartbeat`；前端 EventSource 替代 2.5s 轮询，断线自动重连（test-setup.js 已有 MockEventSource）。
- **风险**：http.server 单线程阻塞 → 推送期间不能处理其他请求；`_sse` 必须异步/独立线程处理；多客户端订阅表。
- **验收**：双客户端同时收到事件；断线重连后补齐缺口（可选 Last-Event-ID）。

### 难点 4：审批/澄清路由（P1）
agent 需要老板拍板时（如采纳经验卡、改卷目标、超限仲裁），面板实时弹窗决策。
- **对策**：新表 `pending_interactions`（session_id/agent/kind(approval|clarify)/payload/status/created_at/expires_at/resolved_at/resolution）；API：`POST /api/meetings/interactions/respond`；超时过期 + 幂等（同一 interaction 只能响应一次）。
- **验收**：请求→弹窗→响应→事件广播→过期清理全路径测试。

### 难点 5：会议消息独立表与增量写入（P1）
现在 transcript 是 JSON 内嵌，无法增量/检索/流式。
- **对策**：新表 `meeting_messages`（session_id/from_agent/role/kind/body/mentions JSON/status/created_at/seq），会议页改从表读取；旧会话 transcript 兼容读取（表为空时回退 JSON）。
- **验收**：迁移幂等；旧会话可见；新会话消息可增量追加。

### 难点 6：长会议上下文压缩（P1）
参考 hermes 的 token 预算/尾截断/摘要锚点，强化现有 `compress_history`。
- **对策**：free 模式按 token 阈值触发压缩；压缩摘要保留六段结构要点与决策；会议消息表记录 `compressed_at` 锚点；摘要作为后续发言上下文注入。
- **验收**：模拟 500+ 条消息会议，上下文不超预算；压缩后关键决策不丢。

### 难点 7：前端聊天室重写（P1）
React 会议中心改为房间形态：消息流（虚拟列表）、输入框（@插入）、成员轨道（头像+思考状态+typing）、审批弹窗、模式切换。
- **对策**：复用现有组件库（AgentAvatar/Button/Input/Dialog/Tabs）；@插入用 mention-options 式列表；消息流用 motion 入场动画；SSE 事件驱动增量渲染。
- **验收**：交互测试（@插入、发消息、审批弹窗、模式切换）+ 视觉验收截图。

### 难点 8：并发、幂等与断线（P1）
轮询与 SSE 并存期、advance 重复提交、agent 并行回复、机器重启恢复。
- **对策**：沿用 preflight 原子锁思路（会议推进加 session 级锁）；advance 幂等（同一 instruction 指纹去重）；SSE 断线后页面拉全量消息补齐；重启后 free 模式会话可恢复（消息表持久）。
- **验收**：并发 advance 只执行一次；断线重连消息不重复。

### 难点 9：向后兼容与回归（P2）
周会（architect_weekly）、六段发言、报告落盘、留痕全部不能破坏。
- **对策**：`rounds` 模式路径零改动（新增逻辑走 mode 分支）；全量测试回归；旧 transcript 兼容。

## 6. 工程表（分阶段实施）

| 阶段 | 内容 | 验收 | 测试与审查 | 回退 |
| --- | --- | --- | --- | --- |
| 0 | 决策记录落盘（本文档）；数据层：`meeting_messages`、`pending_interactions` 表，幂等迁移；`meeting_sessions.mode` 字段 | 迁移重复执行不报错；后端全量测试绿 | 迁移幂等测试；主 agent 自审 | 删表回滚（数据可重建） |
| 1 | 后端 @提及解析（中文边界，参考 hermes mention-routing 移植）+ `meeting_executor.py` 执行器桥（材料/周记/心情注入 + 六段发言 + 工具调用兜底） | dry-run：@单人/@多人/@all 正确路由；发言落 meeting_messages；失败显式留痕 | @路由单测（中文/边界/去 token）；执行器 dry-run；步间审查 | 模式开关关闭即回退旧路径 |
| 2 | free 模式状态机：advance 语义扩展（指令/@消息入队）、串行队列、主席随时总结、与 rounds 并存 | free 模式 dry-run 全链；rounds 旧会话不回归 | 状态机迁移测试；并发 advance 幂等测试；步间审查 | mode 字段默认 rounds |
| 3 | 审批/澄清路由：pending_interactions API + 超时过期 + 幂等响应 + 事件 | 请求→响应→过期全路径测试 | 幂等/过期/越权测试；步间审查 | 事件仅新增，不阻塞旧流程 |
| 4 | SSE 会议事件流：`/api/meetings/events` + 多客户端订阅 + 心跳 | 双客户端同收事件；断线重连 | SSE mock 测试；连接数/阻塞验证；步间审查 | 前端可切回轮询 |
| 5 | 前端聊天室重构（MeetingsPage → 房间视图：消息流/输入/@插入/成员轨道/审批弹窗/模式切换/SSE 接入） | 交互测试 + 视觉截图验收 | 页面组件测试；前端全量回归；视觉抽查 | 保留旧页面路由待切换 |
| 6 | 上下文压缩增强：token 阈值 + 尾截断 + 摘要锚点 + 压缩事件 | 500+ 消息会议不超预算；决策不丢 | 长会议模拟测试；压缩结果断言 | 压缩阈值可配置关闭 |
| 7 | 全量回归 + dry-run 端到端 + 真实会议一次（可选） | 前端 40+ 测试、后端 511+ 测试全绿；真实会议可发起/围观/审批/总结 | 分片全库审查产出 P0–P3 报告并修复 | 分支隔离 |
| 8 | 文档与部署：README 会议章节、backlog 更新、提交推送（待用户确认后收尾） | 文档与代码一致；无敏感信息 | 文档核对；收尾审查 | — |

## 7. 最终验收标准

- 会议支持 `rounds`（现状）与 `free`（实时群聊）两种模式，一键切换且互不破坏。
- 老板可在直播中 @指定编辑、插入指示、响应审批；所有操作实时可见（SSE）。
- 会议消息独立落库、增量读取、旧会话兼容；长会议自动压缩不爆上下文。
- 周会报告、六段发言、留痕、知识库、人物卡链路全部不回归。
- 前端 40+ 测试、后端全量测试全绿；impeccable 设计门禁通过。

## 8. 假设与默认

- 不引入 Node/Socket.IO/Vue；SSE 单向推送满足会议直播需求（上行复用现有 POST）。
- hermes 仅作算法与交互参考，不搬运代码；`mention-routing` 逻辑按 MIT/Apache 许可参考移植（标注来源）。
- `mode` 默认 `rounds`；free 模式为增量能力，可随时关闭。
- 审批/澄清 v1 只服务会议内拍板，不扩展日更/收工链路。
- 转交链（handoff）列为 later：free 模式稳定后再评估，不在本工程表。
- 会议消息表独立于 agent_messages（横向协作）与 weekly_meetings（报告落盘），三者职责分离。
