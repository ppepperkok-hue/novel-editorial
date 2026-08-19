# M5 实施真元文档（自然行为与自由意志 · N13 作品结构管理与创作进度）

## 总览

- **大阶段**：M5 自然行为与自由意志主线（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N1–N7 / N16 / N17 已收口）。
- **当前只拆 N13**（作品结构管理与创作进度，P0 候选 / G1 + G4，依赖 M3 全部；用户已审查通用性并确认升核心主线）。
- **N13 一句话**：作品可组织成可选的层级结构（卷 / 章 / 篇目），大纲作为可选的创作计划版本演进，创作进度（创作中 / 已完成 / 搁置）可跟踪——短篇、长篇、诗集、同人等各类作品共用一套通用骨架。
- **现状**：
  - Workspace 只有 title / genre / description，没有结构、大纲、进度状态；
  - Draft 有 title / status（draft / awaiting_decision / accepted 等），是平铺的章节草稿，没有父级组织；
  - 记忆包（build_memory_pack）有章纲占位，但章纲不可编辑、不可版本化。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「不建任何结构/大纲的作品所有既有创作命令照常跑通（零章节合法）→ 建卷建章 → 挂草稿到章 → 写大纲并修订 → 进度状态流转 → work show 可见」的端到端用例；结构、大纲、进度全部可选，无强制关卡。

## 红线（本阶段强制，06 通用性红线继承）

1. **体裁自适应（红线 5 继承）**：结构层级全部可选——零卷、零章、零大纲均合法；不建结构不改变任何既有命令行为与输出。
2. **大纲不是前置（红线 1/2 继承）**：大纲是可选的创作计划，只随创作自然沉淀与版本演进，绝不构成「先写大纲才能写正文」的强制节点；无大纲时记忆包/视图行为与现在一致。
3. **进度是状态不是关卡（红线 1 继承）**：创作中 / 已完成 / 搁置只是可跟踪标记，不阻塞 talk / draft / decision / review 任何命令；搁置作品可随时恢复继续创作。
4. **结构不绑架草稿**：结构节点只是组织视图，既有平铺草稿机制不破坏；草稿可挂在节点上（可选引用），未挂载的草稿照常存在。

## 地基影响评估（先评估再动工）

- 表结构增量（纯追加，走新 Alembic migration）：
  - `workspace_structure_nodes`：id / workspace_id / parent_id（可空，根节点）/ kind（volume | chapter | section）/ title / sort_order / status（writing | completed | shelved）/ draft_id（可空，可选引用）/ created_at / updated_at；同一 workspace 内 parent 环校验（结构树）；
  - `outlines`：id / workspace_id / content / version（从 1 递增）/ reason / actor / created_at；每部作品最多一条「当前大纲」，修订生成新版本行；
  - `workspaces` 新增列 `status`（String(20)，默认 `writing`，允许 writing | completed | shelved）。
- 配置：不新增配置项；事件契约沿用 SYSTEM 事件 + payload kind（structure_created / structure_renamed / structure_moved / structure_removed / outline_created / outline_revised / workspace_status_changed），不新增 EventType 枚举。
- 依赖方向（cli → core → store）不变；错误码沿用既有枚举（NOT_FOUND / USAGE_ERROR）。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 J1：结构树模型与进度迁移

### 做什么

- `store/models.py`：新增 `WorkspaceStructureNode`、Workspace 增 `status` 列（默认 `writing`）。
- 新 Alembic migration：建 `workspace_structure_nodes` + `workspaces.status` 列，纯追加，既有行安全。
- `core/structure.py`（新模块）：
  - `create_node(db, workspace_id, *, kind, title, parent_id=None, draft_id=None, sort_order=None)`：校验 kind 合法、parent 存在且同作品、parent 层级合法（volume 下可 chapter，chapter 下可 section；同级可任意并列）；返回节点；
  - `list_structure(db, workspace_id)`：返回有序树（sort_order、created_at 兜底）；零节点返回空；
  - `rename_node(db, workspace_id, node_id, title)`；
  - `move_node(db, workspace_id, node_id, parent_id=None, sort_order=None)`：环检测（不能移到自己的子树）、层级校验；
  - `remove_node(db, workspace_id, node_id)`：级联删除子树（纯结构组织，不删草稿本体）；
  - `set_node_status(db, workspace_id, node_id, status)` / `set_workspace_status(db, workspace_id, status)`：三态校验；
  - `count_structure(db, workspace_id)`：卷 / 章 / 篇目计数与已完成计数（章级 completed 计入）。
- tests：建树/层级校验/环检测/移动/级联删除/排序确定性/三态校验/计数；零结构空树；跨作品隔离；status 默认值与迁移回填。

### 做到什么程度

- 结构树与进度状态模型落地且有单测；既有 676 测试全绿（不接 CLI、不改既有命令输出）。

### 验收标准

- 单测覆盖上述全部路径；零结构作品的既有行为零回归。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI 与可见性接入（J2）、大纲版本化（J2）、结构自动生成、从草稿状态自动推导节点完成、多写手并行（N14）。

## 子阶段 J2：CLI、大纲版本化与可见性接入

### 做什么

- `core/outline.py`（新模块）：
  - `create_outline(db, workspace_id, *, content, actor, reason="initial")`：无大纲时创建 v1；已有大纲报 USAGE_ERROR（须走 revise）；
  - `revise_outline(db, workspace_id, *, content, reason, actor)`：无大纲报 NOT_FOUND；版本 +1，留 SYSTEM 事件 `outline_revised`；返回当前大纲与版本；
  - `get_outline(db, workspace_id)`：无大纲返回 None；
  - `list_outline_versions(db, workspace_id, limit=20)`：按版本倒序。
- `cli/structure.py`（新命令组 `structure`）：
  - `structure add <作品ID> <kind> <标题> [--parent <节点ID>] [--draft <草稿ID>] [--order N]`；
  - `structure list <作品ID>`（树形缩进输出，含状态与草稿标题）；
  - `structure rename <作品ID> <节点ID> <新标题>`；
  - `structure move <作品ID> <节点ID> [--parent <节点ID>|--root] [--order N]`；
  - `structure remove <作品ID> <节点ID>`；
  - `structure status <作品ID> <节点ID> <writing|completed|shelved>`。
- `cli/outline.py`（命令组 `outline`）：`outline create` / `outline revise` / `outline show` / `outline history`。
- `cli/works.py`：`works status <作品ID> <writing|completed|shelved>`；`works show` 追加作品状态行与结构树（有结构才显示，零结构输出与现在一致）。
- `core/draft.py` 的 `build_memory_pack`：章纲段改为读取当前大纲（无大纲时维持「暂无（占位）」文案不变）。
- `cli/app.py` registry：注册 structure / outline 命令组。
- tests：全部 CLI 端到端（建卷/章/篇目、挂草稿、移动、级联删除、三态流转、大纲创建/修订/历史、work show 输出变化与零结构不变、记忆包大纲段）；事件留痕断言。

### 做到什么程度

- 端到端可断言：零结构作品所有既有命令输出逐字不变 → 建结构 → 挂草稿 → 大纲创建与修订 → 进度流转 → work show / structure list 可见；
- 大纲无则章纲占位文案与既有断言一致；有则注入当前大纲内容。

### 验收标准

- 端到端用例 + 失败路径（非法 kind、环移动、父级跨作品、三态非法、大纲重复创建、无大纲修订）；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 结构自动生成、进度自动推导、多写手并行（N14）、灵感素材库（N15）、章级草稿状态机改造。

## 子阶段 J3：文档、全量回归与收口

### 做什么

- docs/usage.md 新增「作品结构与创作进度（N13）」节：structure / outline / works status 命令、树形输出、三态语义、零结构合法与红线复述；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 676+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 图形面板结构视图（N12 一并后置）、多作品聚合进度（N10 时再议）、自动生成结构。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。
- 后续单元（N14 / N18 / N10）在 N13 收口后按 backlog 顺序另拆。

## 状态

- 立项（2026-08-20）：实施文档就绪，用户授权低价窗口内自主推进，拆包 J1。
