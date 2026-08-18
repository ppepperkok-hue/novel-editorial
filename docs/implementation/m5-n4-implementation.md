# M5 实施真元文档（自然行为与自由意志 · N4 编辑部讨论形态）

## 总览

- **大阶段**：M5 自然行为与自由意志（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N1/N2/N3/N4/N16）。
- **当前只拆 N4**（编辑部讨论形态，P1 / G1）；N17 记忆衰减与归档只保留方向，不预拆细节（05a 纪律）。
- **N4 一句话**：作者就关键方向/大纲发起一轮有结构的多方讨论——点将（选参与伙伴）、通气（抛出议题）、发言（各伙伴表态）、总结（总编归纳分歧）、落盘（作者拍板 + 行为沉淀），大决策前有一次真实碰撞；讨论是自然协作形态，不是流程关卡。
- **现状**：
  - talk send 只支持作者与单个伙伴的一对一往返；没有多方同议题的讨论通道；
  - N1 主动行为（含总编 proactive_direction「先把方向捋清楚」的自然召集）、N2 立场拒绝/重申/推翻、N3 行为留痕、N16 互委对话模型均已就绪，可作为讨论的底座；
  - 总编的 proactive_direction 已经能在自然触发点召集方向讨论，N4 补齐「召集之后怎么把讨论跑起来并落盘」的形态。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「作者点将发起 → 多方表态（含至少一次立场拒绝）→ 总编总结 → 作者拍板 → 全程留痕」的端到端用例；拒绝继续遵循 N2 立场规则；讨论不成为任何业务的前置关卡（06 红线 1）。

## 红线（继承 06 清单，本阶段强制）

1. **讨论是可选的，不是关卡**：讨论只由作者主动发起（或伙伴通过既有 proactive_direction 提议后由作者确认发起），不出现「必须讨论才能写/改/过稿」的强制节点；伙伴可拒绝参与某个议题，作者可随时拍板结束，拒绝不阻塞其他伙伴发言，也不阻塞作者决策。
2. **发言是对话，不是工单**：一轮讨论就是若干条带 payload 标记的对话消息，不引入议程状态机、发言轮次表、超时、催办等调度器语义。
3. **判断权不变**：参与伙伴对议题行使 N2 判断——议题撞上立场规则时照常拒绝并留痕（拒绝是一次表态，不是事故）；作者永远可介入、可拍板。
4. **只报告不代笔**：总结只归纳各方立场与分歧，不代作者做最终决定，不产出正文内容。

## 地基影响评估（先评估再动工）

- 无表结构变更、无迁移：开场/发言/总结/拍板全部走既有 messages（payload 标记）与 events（agent.message）。
- 事件契约、错误码、依赖方向（cli → core → store）不变；错误路径沿用 NovelError(USAGE_ERROR / NOT_FOUND)。
- 行为沉淀复用 N3 behavior_timeline（viewpoint / relationship），不新增 kind。
- 若实现中发现必须改表结构 / 事件契约 / 错误码，先停下回报，不硬做。

## 子阶段 E1：讨论数据模型与 CLI 骨架

### 做什么

- 新建 `src/novel_editorial/core/discussion.py`：
  - `open_discussion(db, workspace_id, *, topic, participants: Sequence[Agent]) -> tuple[str, Message]`：校验 topic 非空、participants 非空、角色不重复；生成 discussion_id（`uuid4().hex`）；落一条 role=author、actor=作者 的开场消息（内容「作者发起讨论「{topic}」（参与：A、B、C）」），payload `{"kind": "discussion_open", "discussion_id": ..., "topic": ..., "participants": [名字...], "convener": "作者"}`；同步 agent.message 事件。
  - `contribute_to_discussion(db, workspace_id, *, discussion_id, topic, agent) -> Message`：E1 先不做立场拒绝（留给 E2），只落一条 role=agent 的确定性表态（按角色模板、插值 topic），payload `{"kind": "discussion_contribution", "discussion_id": ..., "topic": ..., "position": "stated"}`；四角色各一段固定、可断言的文案（总编定基调、责编谈节奏、写手守人设、审稿盯一致性）。
  - `summarize_discussion(db, workspace_id, *, discussion_id, topic, summarizer: Agent) -> Message`：按 discussion_id 取回全部发言（payload LIKE 匹配，沿用既有习惯），生成确定性总结文案，逐个列出「{名字}：{发言内容或拒绝口径}」并标注同意/分歧；落一条 role=agent、actor=summarizer 的总结消息，payload `{"kind": "discussion_summary", "discussion_id": ..., "topic": ..., "positions": [{"agent": 名字, "position": "stated|refused", "content": ...}, ...]}`。E1 不接行为沉淀（留给 E2）。
  - `conclude_discussion(db, workspace_id, *, discussion_id, topic, outcome: str) -> Message`：校验 outcome 非空；落一条 role=author 的拍板消息（内容「作者拍板：{outcome}」），payload `{"kind": "discussion_decision", "discussion_id": ..., "topic": ..., "outcome": ...}`。
- CLI（talk 组新增命令）：
  - `talk discuss <作品ID> --topic <文本> [--with <别名,别名>] [--outcome <文本>]`：`--with` 缺省为全部四伙伴（总编/责编/写手/审稿），按固定顺序发言；流程 = open → 各伙伴 contribute → 总编 summarize → （有 outcome 时）conclude；每步回显一行。
  - 校验：topic 非空；`--with` 里的别名必须是不同伙伴（作者、未知别名、重复角色均报用法错误）。

### 做到什么程度

- 开场/发言/总结/拍板四类消息与 payload 可断言（messages 与 events 数量、payload 结构稳定）；
- 一条 `talk discuss` 命令走完整流程，输出可读、可复现（mock 下确定）；
- 既有 429 测试全绿，无 N2/N3 接入（E2）。

### 验收标准

- 单测：payload 结构、topic/outcome 空报用法错误、`--with` 校验（作者、未知别名、重复角色）、未知 discussion_id 报 NOT_FOUND、participants 为空报用法错误。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 立场拒绝接入（E2）、行为沉淀接入（E2）、多轮协商、LLM 自由发言、自然触发召集的闭环（E3 文档说明）。

## 子阶段 E2：立场拒绝与行为沉淀接入

### 做什么

- `contribute_to_discussion` 接入 N2 立场判断（口径与 talk send / delegation 一致）：
  - 议题命中 `check_refusal(agent, topic)` 且未被作者推翻时，发言 = 拒绝表态：payload `{"kind": "discussion_contribution", "discussion_id": ..., "topic": ..., "position": "refused", "rule": ..., "stance": ...}`（重复命中加 `"repeated": true`，文案用 refusal/reaffirmation）；
  - 命中但已被作者推翻过（`has_same_rule_override`）时按正常表态走；
  - 正常表态保持 E1 文案，payload position="stated"。
- `summarize_discussion` 末尾追加 N3 沉淀（`record_behavior_entry_safe`，失败降级告警不回滚）：
  - 每位发言伙伴一条 viewpoint（target=topic、after_value=表态摘要（正常=「表达了立场」/ 拒绝=「拒绝参与该议题并坚持立场」）、source=`discussion:{discussion_id}`）；
  - 发言伙伴 mood 更新为 MOOD_TALK（复用 `update_agent_mood`，讨论即投入）。
- `conclude_discussion` 拍板后追加：总编 → 作者 relationship（summary="讨论拍板落盘"、source=`discussion:{discussion_id}`）？——**不引入多余沉淀**：拍板本身是作者行为，不额外造关系条目；仅在 `conclude_discussion` 记录消息。沉淀范围以发言 viewpoint + mood 为界。

### 做到什么程度

- 端到端：作者点将 → 多方表态（至少一人议题撞立场而拒绝、其余正常）→ 总结标注分歧 → 作者拍板 → messages/events 与 behavior_timeline 的 viewpoint 条目均可断言；
- 拒绝不阻塞：有伙伴拒绝时，其余伙伴照常发言、总结照常生成、作者照常拍板；
- 沉淀写入失败时讨论结果不变、有 warning；
- 既有 429 测试全绿，smoke_m3 仍 SMOKE OK。

### 验收标准

- 端到端两态（全正常 / 含拒绝）+ 失败路径（monkeypatch 沉淀写入抛错，业务仍成功）；
- 立场历史跨通道复用：同一条规则在 talk 或互委里拒绝过，讨论中再命中时按重申口径。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 多轮协商与来回辩驳、发言语气多样性（先固定文案，后续 LLM 生成）、印象/关系数值化（N3 已明确不做数值权重）。

## 子阶段 E3：可见性、文档与收口

### 做什么

- talk list 对四类讨论消息补最小标记：`[author·讨论·开场]` / `[agent·讨论·发言]` / `[agent·讨论·总结]` / `[author·讨论·拍板]`，其余标记不回退；events list 原有 agent.message 输出不变。
- docs/usage.md 补「编辑部讨论形态（N4）」节：`talk discuss` 命令、点将/通气/发言/总结/落盘语义、拒绝与 N2 立场、沉淀与 N3 留痕、讨论非关卡说明、与总编 proactive_direction 自然召集的关系；示例 mock 实跑。
- 全量回归 + 审查。

### 做到什么程度

- 作者能通过 talk list 看到一轮讨论从开场到拍板的全程，且能分辨谁拒绝了、谁同意；
- 文档与行为一致、示例可复现；
- 全量 429+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- talk list 标记与 payload 可断言；文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板/可视化（后置）；讨论统计报告（N10）；LLM 自由发言与多轮协商（N4 后续增量再议）；伙伴完全自主点将（N1 扩展，后续再议）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N17）在 N4 收口后再拆。

## 状态

- 立项（2026-08-18）：实施文档就绪，用户确认后拆包 E1。
- E1 完成（2026-08-18；commits ebbed7b / 44dba7f，全量 453 测试绿；讨论数据模型与 CLI 骨架 + 独立审查 P3 修复，审查链归档 docs/reviews/）。E2 待拆包。
- E2 完成（2026-08-18；commits 6962088 / bc71c99，全量 463 测试绿；N2 立场拒绝与 N3 沉淀接入 + 独立审查两条意见修复，审查链归档 docs/reviews/）。E3 待拆包。
- E3 完成（2026-08-18；commits 56c4d1c / 1d8f5a4，全量 465 测试绿；talk list 讨论标记 + usage 文档 + 注册清单补漏，审查链归档 docs/reviews/）。
- N4 收口（2026-08-18）：全量 465 测试、ruff、pyright、宪法、smoke_m3、stress_m3 全绿；编辑部讨论形态整体交付，红线（讨论非关卡、发言非工单、拒绝不阻塞、总结不代笔）全程未破。后续单元 N17 按 backlog 顺序待用户立项拆包。
