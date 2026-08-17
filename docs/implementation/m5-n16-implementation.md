# M5 实施真元文档（自然行为与自由意志 · N16 协作网络伙伴互委）

## 总览

- **大阶段**：M5 自然行为与自由意志（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N1/N2/N3/N4/N16）。
- **当前只拆 N16**（协作网络 / 伙伴互委，P0 / G1 + G3）；N4 编辑部讨论形态只保留方向，不预拆细节（05a 纪律）。
- **N16 一句话**：伙伴之间可以互相委托并回应——写手请审稿看逻辑、责编请写手改稿，协作网络不只围着作者转；委托是对话不是工单。
- **现状**：
  - talk send 只支持作者 @ 伙伴的单向路由；伙伴之间没有互委与回应的通道；
  - 拒绝/推翻（N2）、主动行为（N1）、行为留痕（N3）已就绪，可作为互委的判断与沉淀底座；
  - relationship_presets 静态，尚无伙伴间互动演化（N3 已提供 behavior_timeline 承载）。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条"伙伴 A 委托伙伴 B → B 接受/拒绝 → 全程留痕"的端到端用例；拒绝继续遵循 N2 立场规则；不引入任务队列/认领/超时（06 红线）。

## 红线（继承 06 清单与 backlog 取舍原则，本阶段强制）

1. **对话委托，不工单化**：一次委托是一条对话消息，不引入任务队列、认领状态机、超时惩罚、催办提醒；被委托方不承诺完成时限。
2. **判断权不变**：被委托方可接受、可拒绝；命中 N2 立场规则时照常拒绝并留痕；作者永远可介入、可拍板。
3. **兼容 N1-N3**：委托与回应走既有 messages / events（agent.message），payload 新增 kind=delegation / delegation_response，事件契约类型不变；拒绝、关系、印象的沉淀走 N3 behavior_timeline，不回滚业务。

## 地基影响评估（先评估再动工）

- 无表结构变更、无迁移：委托与回应继续用 messages（payload 标记）与 events（agent.message）。
- 事件契约、错误码、依赖方向（cli → core → store）不变；错误路径沿用 NovelError(USAGE_ERROR / NOT_FOUND)。
- 若实现中发现必须改表结构 / 事件契约 / 错误码，先停下回报，不硬做。

## 子阶段 D1：委托与回应的对话模型

### 做什么

- `core/delegation.py`（新建）：
  - `record_delegation(db, workspace_id, from_agent, to_agent, task)`：落一条 role=agent、actor=from_agent.name 的 messages（payload `{"initiator": "agent", "kind": "delegation", "from": <名字>, "to": <名字>, "task": <文本>}`）+ agent.message 事件；无队列、无状态机。
  - `respond_to_delegation(db, workspace_id, from_agent, to_agent, task)`：先用 check_refusal(to_agent, task) 判定——命中立场规则则回应为拒绝（payload `{"initiator": "agent", "kind": "delegation_response", "decision": "refused", "rule": ..., "stance": ...}`，文案用规则 refusal/reaffirmation 口径），否则回应接受（decision="accepted"，确定性文案如「收到，我这就看。」）；回应同样落 messages + agent.message 事件。
- CLI（talk 组新增命令）：
  - `talk delegate <作品ID> <to别名> --as <from别名> --task <文本>`：校验 from/to 是不同伙伴别名（作者不可作为 from/to）、task 非空；依次调用 record_delegation 与 respond_to_delegation，回显委托与回应两行。

### 做到什么程度

- 委托与回应可断言（messages 两条、events 两条、payload 结构稳定）；
- 拒绝分支与接受分支都走通（mock 下确定）；
- 既有 394 测试全绿，无行为沉淀接入（D2）。

### 验收标准

- 单测：payload 结构、from/to 校验（作者、相同伙伴、未知别名均报用法错误）、task 空报用法错误、拒绝/接受两种回应。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- LLM 自由回应（先确定性文案）、多轮协商、超时/催办、行为沉淀（D2）、自然触发与文档（D3）。

## 子阶段 D2：立场拒绝与行为沉淀接入

### 做什么

- 回应后追加 N3 沉淀（record_behavior_entry_safe，失败降级告警不回滚）：
  - 接受：from_agent → to_agent 的 relationship（summary="委托被接受"，source="delegation:accepted"）与 impression（summary="可协作"，source="delegation:accepted"）；
  - 拒绝：to_agent 的 viewpoint（target=rule、after="坚持该立场"、source=f"refusal:{rule}"，口径与 N2 一致）与 from_agent → to_agent 的 relationship（summary="委托被拒绝"，source="delegation:refused"）。
- 确认响应拒绝不影响作者后续介入：接受/拒绝都不是关卡。

### 做到什么程度

- 端到端：A 委托 B → 接受/拒绝 → messages/events 与 behavior_timeline 三类条目均可断言；
- 沉淀写入失败时委托与回应结果不变、有 warning；
- 既有 394 测试全绿，smoke_m3 仍 SMOKE OK。

### 验收标准

- 端到端两态（接受/拒绝）+ 失败路径（monkeypatch 写入抛错业务仍成功）。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 伙伴完全自主发起互委的触发（N1 扩展，后续再议）、印象/关系数值化、多写手网络（N14）。

## 子阶段 D3：可见性、文档与收口

### 做什么

- talk list 对 delegation / delegation_response 补最小标记：`[agent·互委·委托]` / `[agent·互委·回应]`，其余标记不回退；
- docs/usage.md 补「协作网络（伙伴互委）」节：委托命令、接受/拒绝语义、留痕与 N3 沉淀、不工单化说明；示例 mock 实跑；
- 全量回归 + 审查。

### 做到什么程度

- 作者能通过 talk list / events list 看到委托与回应全程；
- 文档与行为一致、示例可复现；
- 全量 394+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- timeline 标记与事件 payload 可断言；文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板/可视化（后置）；互委统计报告（N10）；编辑部讨论形态（N4）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N4 / N14 / N17）在 N16 收口后再拆。

## 状态

- D1 / D2 / D3：待用户确认本文档后派包。
