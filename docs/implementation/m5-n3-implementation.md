# M5 实施真元文档（自然行为与自由意志 · N3 行为留痕与演化）

## 总览

- **大阶段**：M5 自然行为与自由意志（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N1/N2/N3/N4）。
- **当前只拆 N3**（行为留痕与演化，P0 / G3 + G4）；N4 编辑部讨论形态只保留方向，不预拆细节（05a 纪律）。
- **N3 一句话**：伙伴的行为（拒绝 / 坚持 / 反驳 / 推翻 / 拍板 / 收意见）在事后追加沉淀为印象、关系与观点变化，形成可查询的演化时间线；情绪继续沿用既有 mood 流转，越协作越有来历。
- **现状**：
  - mood 字段 + 固定流转（talk / revise / accept / reject）已落地，mood_change 落 messages、agent.message 落 events（N2 前身）；
  - 拒绝/重申/推翻（kind=refusal/override，带 stance/rule）、反驳（kind=rebuttal，带 targets）已可追溯（N2）；
  - relationship_presets 只是 DEFAULT_BAND 里的静态文本，没有按互动演化；印象与观点变化没有存储。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；印象 / 关系 / 观点三类条目各至少一个端到端用例；时间线与当前状态可查询；既有 354 测试全绿；不设强制关卡（06 红线 1）。

## 红线（继承 06 清单，本阶段强制）

1. 留痕是**事后追加的沉淀，不改变既有行为语义**：拒绝、推翻、主动、拍板仍按 N1/N2 口径运行，N3 只追加记录，不得出现"必须积累多少印象/关系才能继续"的关卡；沉淀写入失败不回滚业务结果。
2. 不引入任务队列、认领状态机、超时惩罚等调度器语义（不工单化）。
3. 兼容 N1/N2：既有 payload、mood 流转、talk/draft/decision 行为不破坏；沉淀写入失败按 proactive 模式降级并显式告警，不静默吞错。

## 地基影响评估（先评估再动工）

- **新增一张表 `behavior_timeline`**（Alembic 迁移，加性变更，不重写旧数据）：
  - 字段：id / workspace_id / agent_id（谁的记录）/ kind（impression | relationship | viewpoint）/ target（对方 actor 名或规则主题）/ summary / before_value / after_value（观点或关系变化时使用，可空）/ source（来源事件与规则，如 `refusal:writer_portrayal`）/ created_at。
  - 事件溯源式：当前印象 / 关系 / 观点 = 按（agent, kind, target）取最新条目；完整过程靠时间线查询。
- 事件契约、错误码、依赖方向（cli → core → store）不变；CLI 命令注册在 `cli/`、业务在 `core/`、访问在 `store/`。
- 若实现中发现必须改事件契约 / 错误码 / 既有表，先停下回报，不硬做。

## 子阶段 C1：行为留痕模型与迁移

### 做什么

- `store/models.py` 新增 `BehaviorTimeline`；Alembic 迁移新增 `behavior_timeline` 表（每部作品库自动升级）。
- `core/behavior.py`（或按最小改动并入既有 core 模块）提供：
  - `record_behavior_entry(...)`：按 kind/target/summary/before/after/source 追加一条，kind 白名单外抛用法错误；
  - `list_behavior_timeline(...)`：按 agent / kind / limit 查询，时间升序或倒序；
  - `current_behavior_state(...)`：按（agent, kind, target）取最新条目的当前值。

### 做到什么程度

- 新表在新建作品库与既有作品库升级后均可用；迁移幂等；
- 追加 / 列表 / 当前状态三组服务有单测；非法 kind 报用法错误；
- 既有 354 测试全绿，无行为接入（留给 C2）。

### 验收标准

- 单测：迁移后表结构可用；roundtrip；kind 白名单；当前状态取最新；时间线排序。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 关键行为接入（C2）、CLI 可见性与时间线（C3）、记忆衰减（N17）、面板/可视化。

## 子阶段 C2：关键行为接入

### 做什么

- 在既有业务写入**之后**追加沉淀（失败降级并告警，不回滚业务，仿 proactive 模式），确定性规则 mock 下可断言：
  - **观点（viewpoint）**：某 rule 首次拒绝 → `source=refusal:<rule>`、`after=坚持该立场`；作者推翻 → `source=override:<rule>`、`before=坚持该立场`、`after=按作者决定执行`。
  - **关系（relationship）**：作者推翻 → 写手对作者的条目（作者拍板优先）；伙伴意见（review add from agent）→ 写手对该伙伴的条目（被指出问题 / 被退稿）；拍板 accept / reject → 写手对作者的条目（稿子被认可 / 被退回）。
  - **印象（impression）**：伙伴意见 → 写手对该伙伴的印象（盯逻辑 / 盯节奏等，按角色取值）；拍板 → 写手对作者的印象（认可产出 / 要求高）。
- 情绪继续沿用既有 mood（mood_change 消息与事件已留痕），不重复落 behavior_timeline。

### 做到什么程度

- 印象 / 关系 / 观点三类各至少一个端到端用例：触发既有命令 → 追加条目（内容、source、before/after 可断言）；
- 沉淀写入失败时业务结果不变、有显式 warning；
- 既有 N1/N2 行为与 354 测试不破坏。

### 验收标准

- 端到端：refusal → viewpoint；override → viewpoint（before/after）+ relationship；review add → impression + relationship；decision accept/reject → impression + relationship；
- 失败路径：monkeypatch 写入抛错，业务命令仍成功且输出 warning。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3（确认追加不拖慢不刷屏）。

### 暂不做

- 印象/关系的数值化评分与权重、概率化行为、多写手网络（N16）、观点冲突自动调解（N4）。

## 子阶段 C3：可见性、时间线与文档

### 做什么

- CLI 新增（动词-宾语）：
  - `behavior timeline <作品ID> [--agent <别名>] [--kind ...] [--limit N]`：按时间回放印象 / 关系 / 观点变化，带 source 与 before/after；
  - `behavior show <作品ID>`：按伙伴汇总当前印象 / 关系 / 观点状态。
- `agents show` 附带当前印象与关系摘要（最小呈现）。
- docs/usage.md 补「行为留痕与演化」说明：沉淀哪些行为、怎么看时间线与当前状态、失败降级语义；示例 mock 下实跑。

### 做到什么程度

- 作者能通过 CLI 看到"谁对谁积累了怎样的印象 / 关系，观点怎么一步步变的"；
- 文档与行为一致、示例可复现；
- 全量 354+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- timeline / show 输出可断言；agents show 摘要不破坏既有展示；文档示例实跑生效；
- 审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板/可视化（后置）；印象/关系统计报告（N10）；记忆衰减与归档（N17）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N4 / N16 / N17）在 N3 收口后再拆。

## 状态

- C1 完成（2026-08-17；commits abc09b5 / b6973b9，全量 365 测试绿；迁移 f80e112950a2，索引创建与表守卫解耦）。
- C2 / C3：待派包。
