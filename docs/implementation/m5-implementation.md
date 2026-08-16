# M5 实施真元文档（自然行为与自由意志 · N1 主动行为引擎）

## 总览

- **大阶段**：M5 自然行为与自由意志（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N1/N2/N3/N4）。
- **当前只拆 N1**（主动行为引擎，P0 / G1）；N2 判断与立场深化、N3 行为留痕与演化、N4 编辑部讨论形态只保留方向，不预拆细节（05a 纪律）。
- **N1 一句话**：伙伴在自然触发点自主发起协作（写手主动追问设定、责编主动提意见、审稿主动提示矛盾、主编主动召集方向梳理），不需要作者逐条驱动。
- **现状**：仅总编一条固定 `proactive_question`（talk send 后触发一次，`has_proactive_message` 防重复）；事件流已具备（events 表 / agent.message）。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；每个角色至少一种情境可产生主动行为；频次控制生效；开关可关；不设强制关卡（06 红线 1）。

## 红线（继承 06 清单，本阶段强制）

1. 主动行为是**可选的自然协作形态**：触发是情境/概率性的，伙伴与作者均可拒绝；不得出现"必须主动/必须通过某节点才能继续"的强制逻辑。
2. 不引入任务队列、认领状态机、超时惩罚等调度器语义。
3. 现有 `PROACTIVE_QUESTION`（总编首轮提问）行为保留，兼容既有测试；扩展为多角色多情境。

## 子阶段 A1：主动行为模型与配置

### 做什么

- 新增 `src/novel_editorial/core/proactive.py`（或扩展 chat.py，以最小改动为准）：
  - 主动行为类型常量/枚举：`proactive_question`（追问设定）、`proactive_review`（责编主动意见）、`proactive_consistency`（审稿主动提示矛盾）、`proactive_direction`（主编方向梳理）、`proactive_report`（写手主动汇报）；
  - 触发点框架：一组 `(情境, 条件函数)` 评估入口，在既有业务事件后调用（talk send / draft generate / draft revise / review add / decision / style set / memory note）；
  - 频次控制：每作品每伙伴的主动消息上限（默认值可配），超限不再触发；主动消息带 payload `{"initiator": "agent", "kind": "<类型>", "trigger": "<情境>"}`；
  - 配置：`Settings` 新增 `proactive_enabled: bool = True` 与 `proactive_max_per_agent: int = 3`（config.toml `[defaults]` 可覆盖，沿用 NOVEL_* 环境变量约定）。
- 保留现有 `PROACTIVE_QUESTION` / `has_proactive_message` 的对外行为（talk.py 与 demo.py 不破坏）。

### 做到什么程度

- 模型、触发点框架、频次控制、配置全部落地且有单测；
- 现有 259 测试全绿（含 talk/demo 的 proactive 断言）；
- 未接入任何具体角色情境（留给 A2）。

### 验收标准

- 单元测试覆盖：类型注册、条件评估入口、频次上限（超过不触发）、开关关闭不触发、payload 结构。
- 配置：环境变量/TOML 覆盖生效。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 具体角色的主动行为内容（A2）；
- 概率随机化（先用确定性条件，后续再引入概率）；
- 伙伴间主动互委（N16，不在本单元）。

## 子阶段 A2：四角色主动行为落地

### 做什么

- 至少以下情境各一，内容在 mock LLM 下确定、可断言：
  - 写手（proactive_report / proactive_question）：`draft generate` 或 `draft revise` 后主动汇报/追问（例如"这章我留了个钩子，下章要不要收"）；
  - 责编（proactive_review）：`draft generate` 质量门通过后主动给一条跟稿意见（引用正文/风格锚点上下文）；
  - 审稿（proactive_consistency）：`style set` 或 `plot plant` 后主动提示潜在矛盾（引用设定/线索）；
  - 主编（proactive_direction）：作品尚无风格锚点或首轮对话后主动召集方向梳理（与现有 PROACTIVE_QUESTION 融合或并行，保持既有行为不破坏）。
- 触发点挂到对应 CLI 命令（talk/draft/style/plot/decision 等）的业务事件之后，消息落 messages 表、事件落 events 表（agent.message）。

### 做到什么程度

- 四个角色各至少一种情境可产生主动行为（端到端 CLI 测试断言输出与落库）；
- 频次控制对多角色同时生效（连续多轮不刷屏）；
- 与既有流程兼容：主动消息是追加，不阻塞、不改写任何业务结果。

### 验收标准

- 每角色至少一个端到端用例：执行触发命令 → 主动消息出现（CLI 输出 + messages/events 落库 + payload.kind 正确）；
- 上限用例：同伙伴触发超过上限后不再新增主动消息；
- 关闭 proactive_enabled 后任何情境不触发；
- smoke_m3 全链路仍 OK（含 demo 的 proactive 断言）。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3（确认多角色主动行为不拖慢/不刷屏）。

### 暂不做

- 概率/个性化触发权重；
- 主动行为被拒绝后的重试与摩擦（N2/N3）；
- 主动消息的语气多样性（先固定文案，后续让 LLM 生成）。

## 子阶段 A3：可见性、克制与文档

### 做什么

- `talk list` / `events list` 对主动消息可见（payload 带 kind，输出可带标记或保持现状由来源可辨）；
- usage 文档（docs/usage.md）补充主动行为说明与配置项（proactive_enabled / proactive_max_per_agent）；
- 全量回归 + 审查。

### 做到什么程度

- 作者能通过 CLI 看到"这条是伙伴主动发的"（可借助 events payload 或 talk list 来源）；
- 文档与行为一致（配置可关、可调上限）。

### 验收标准

- 文档步骤实测可复现（配置示例生效）；
- 全量 259+ 测试、smoke、stress 全绿。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板/可视化（后置）；
- 主动行为统计/报告（N10 跨作品视图时再议）。

## 影响评估（涉及基底）

- 无表结构变更、无迁移：主动消息走既有 messages 表（payload 标记）与 events 表（agent.message）。
- 配置结构增量：Settings 加两个字段（默认值兜底，不影响现有配置加载）。
- 依赖方向不变：cli → core（proactive 在 core），事件契约不变。
- 若实现中发现必须改表结构/事件契约/错误码，先停下回报，不硬做。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N2/N3/N4）在 N1 收口后再拆。

## 状态

- A1：完成（24a9b32 + 3769382 + ebe32dd + d9c0cc1，审查链收敛 Ready，2026-08-15 归档）。
- A2：完成（A2-A 写手/责编 b644df6 + 66ecb2c；A2-B 审稿/主编 ca7485c + 1fd48de；审查链收敛 Ready，2026-08-15/16 归档）。
- A3：待派包。
