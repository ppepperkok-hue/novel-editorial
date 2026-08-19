# M5 实施真元文档（自然行为与自由意志 · N14 多写手并行班子）

## 总览

- **大阶段**：M5 自然行为与自由意志主线（backlog 见 docs/project-plan/06-new-capability-backlog.md，N1–N7 / N13 / N16 / N17 已收口）。
- **当前只拆 N14**（多写手并行班子，P1 / G1，依赖 N13 结构骨架）。
- **N14 一句话**：一部作品里可配置多位写手分章并行创作，大长篇不用等单写手串行写；协作保持对话委托形态，不引入任务队列、认领状态机或超时惩罚。
- **现状**：
  - 每部作品由 seed_default_band 建四个固定角色，写手只有一个；`get_agent(db, workspace_id, AgentRole.WRITER)` 按角色取写手，`generate_draft` / `revise_draft` / `build_memory_pack` 全部固定用该写手；
  - Draft 没有记录「谁写的」，只有 title / status / current_version；
  - N13 已提供卷/章/篇目结构骨架，节点可挂草稿，但没有按写手分派的概念。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「新增第二位写手 → 用不同写手各生成一章 → draft list 可区分作者 → 各自私有记忆不串 → 不指定写手时默认写手行为与之前完全一致」的端到端用例；全程无队列、无认领、无超时语义。

## 红线（本阶段强制，06 通用性红线继承）

1. **不工单化（红线 3 继承）**：多写手只是「作品里多了几位写手 + 指定谁写」，保持对话委托形态；不引入任务队列、认领状态机、分派表、超时惩罚等调度器语义。
2. **默认行为不变（向后兼容）**：不指定写手时，generate / revise / memory pack 与 N14 之前逐字一致；既有 750 测试中与写手相关的断言零回归。
3. **记忆与产出隔离**：每位写手的私有记忆按 agent 隔离（既有机制），生成/修订按指定写手构建记忆包并留痕 writer_id；不跨写手注入私有记忆。
4. **角色唯一性只对写手放开**：总编 / 责编 / 审稿仍唯一；新增写手名字在作品内唯一（与既有伙伴名冲突报用法错误）。

## 地基影响评估（先评估再动工）

- 表结构增量（纯追加，走新 Alembic migration）：
  - `drafts` 新增列 `writer_id`（String(32)，可空，迁移时回填该作品默认写手 id；纯引用不建外键）。
- 现有 `get_agent` 按角色取写手的行为在多写手下产生歧义：新增按名字/ID 解析优先的服务封装，既有按角色取默认写手的路径只用于「未指定写手」且要求唯一——若作品存在多名写手，未指定时取 seed 顺序第一位（确定性，兼容旧库）。
- 配置：不新增配置项；事件契约沿用既有 DRAFT_CREATED payload（可补 writer 名字字段，向后兼容）；错误码沿用既有枚举。
- 依赖方向（cli → core → store）不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 K1：多写手模型与写手感知的草稿服务

### 做什么

- `core/agents.py`：
  - `create_agent(db, workspace_id, *, name, role, personality="")` 或等价服务：作品内名字唯一（USAGE_ERROR）；role 为 writer 时允许重复实例，其余角色若已存在报 USAGE_ERROR（保持唯一）；
  - `list_agents(db, workspace_id)` 按 created_at 排序（既有）；
  - `get_default_writer(db, workspace_id)`：按 created_at 取第一位 writer（兼容旧库单写手）；无 writer 报 NOT_FOUND。
- `store/models.py`：Draft 新增 `writer_id`（String(32)，可空，默认 None）；新 Alembic migration（down_revision = 当前 head，先确认唯一）加列并回填各作品默认写手 id（按作品遍历，取第一位 writer）。
- `core/draft.py`：
  - `generate_draft(..., writer: Agent | None = None)`：writer 缺省用 get_default_writer；build_memory_pack 按指定 writer 取私有记忆；Draft.writer_id 写入；
  - `revise_draft(..., writer: Agent | None = None)`：缺省沿用草稿的 writer_id（无则默认写手）；修订仍可换人（显式传 writer 时更新 writer_id）；
  - `build_memory_pack(db, workspace_id, writer=None)`：writer 缺省用默认写手（memory pack CLI 不传时行为不变）。
- tests：多写手创建与名字/角色校验；默认写手确定性；generate 指定写手后 draft.writer_id 正确、记忆包按写手隔离；revise 缺省沿用原写手、显式可换人；不指定写手时行为与既有断言逐字一致（既有 draft 测试全绿）；迁移回填默认写手。

### 做到什么程度

- 模型、迁移、服务全部落地且有单测；既有 750 测试全绿（不接 CLI 新参数、不改既有命令输出）。

### 验收标准

- 单测覆盖上述全部路径；默认写手路径与 N14 前行为零回归。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI 接入（K2）、节点级写手指派（后置）、草稿换写手可见性、多写手并行调度语义（永远不做）。

## 子阶段 K2：CLI 与可见性

### 做什么

- `cli/agents.py`：新增 `agents add <作品ID> <role> <名字>`（writer 可多实例，其余角色唯一，名字冲突报用法错误）；`agents list` 新增命令（或复用既有 agents show）；输出含角色与名字。
- `cli/draft.py`：`draft generate <作品ID> [--title X] [--writer <别名|ID>]`；`draft revise <草稿ID> [--reason X] [--writer <别名|ID>]`；`draft list` 输出追加写手名字（格式：`<草稿ID> <标题> (<写手>) <状态> v<N>` 或与既有格式最小差异——以既有输出断言为准做最小扩展）；`draft show` 追加写手行（可选）。
- `cli/memory.py`：`memory note <作品ID> <别名>` 已可按名字解析到具体写手（resolve_agent 支持别名与 ID，多写手下按名字唯一解析）；确认多写手别名解析不歧义（重复名已禁止）。
- tests：端到端「agents add 写手乙 → draft generate --writer 写手乙 → draft list 显示写手乙 → 写手乙 memory note 私有 → 写手乙 generate 只带自己的笔记 → 不指定 writer 仍走默认写手」；非法 role、重复名、未知 writer、非 writer 指定报错路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 做到什么程度

- 端到端可断言：两位写手并行各产一章、可见性可区分、私有记忆不串、默认行为不变。

### 验收标准

- 端到端用例 + 失败路径；既有写手相关断言零回归；smoke_m3 / stress_m3 通过。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 节点级写手指派、写手间互相看稿的协作流（随 N16 形态扩展）、自动轮转/负载均衡（工单化，永远不做）。

## 子阶段 K3：文档、全量回归与收口

### 做什么

- docs/usage.md 新增「多写手并行（N14）」节：agents add 语义与角色唯一性、draft generate/revise --writer、draft list 写手可见、记忆隔离、默认行为不变与不工单化红线；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 750+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 图形面板写手视图（N12 一并后置）、多作品写手池（N10 时再议）、节点级写手分派。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。
- 后续单元（N18 / N10 / N8）在 N14 收口后按 backlog 顺序另拆。

## 状态

- 立项（2026-08-20）：实施文档就绪，用户授权低价窗口内自主推进，拆包 K1。
- K1 完成（2026-08-20；commit 07160c4，全量 762 测试绿；多写手模型、Draft.writer_id 迁移与写手感知草稿服务；解析缺口随 K2 一并补齐）。
- K2 完成（2026-08-20；commits 6a5d617 / f9c0731，全量 779 测试绿；agents add/list、draft --writer、写手可见性 + 独立审查 P3（非 ASCII casefold）修复，审查链归档 docs/reviews/）。K3 待拆包。
- K3 完成（2026-08-20；commit 9bad8fd，全量 779 测试绿；usage 文档章节 + 示例实跑，独立审查 Ready 无意见，审查链归档 docs/reviews/）。
- N14 收口（2026-08-20）：全量 779 测试、ruff、pyright、宪法、smoke_m3、stress_m3 全绿；多写手并行整体交付，红线（不工单化、默认行为不变、记忆与产出隔离、角色唯一性只对写手放开）全程未破。后续单元 N18 / N10 / N8 按 backlog 顺序待立项拆包。
