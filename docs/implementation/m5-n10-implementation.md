# M5 实施真元文档（老板视角与开源 · N10 跨作品聚合视图）

## 总览

- **大阶段**：M8 老板视角与开源（backlog 见 docs/project-plan/06-new-capability-backlog.md，N1–N7 / N13 / N14 / N16 / N17 / N18 已收口）。
- **当前只拆 N10**（跨作品聚合视图，P1 / G1 + G4，依赖 M3 全部与 N13 进度状态）。
- **N10 一句话**：老板一眼看到所有编辑部的状态——待拍板、卡点、产出、进度，同时管理多部作品。
- **现状**：
  - `works list` 只有 id/标题/体裁；单部作品的待拍板（decision pending）、结构进度（structure/works status）、产出（draft list）都要逐部查；
  - 没有跨作品的聚合摘要。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「两部以上作品各造不同状态（待拍板 / 无待办 / 已完成 / 搁置 + 不同结构进度与最近产出）→ works overview 按最近活动排序且每行摘要正确 → 无作品空态」的端到端用例；聚合只读、不阻塞任何创作命令。

## 红线（本阶段强制，06 通用性红线继承）

1. **只读不阻塞（红线 1/2 继承）**：overview 是纯只读聚合命令，不构成任何创作前置；单作品数据读取失败只告警并跳过该作品，不整体失败。
2. **跨作品隔离只读**：聚合只读各作品公开元数据（标题/体裁/状态/待拍板数/结构进度/最近产出时间），不读写任何私有笔记、不触发检索保鲜等副作用。
3. **口径与单作品命令一致**：待拍板数 = decision pending 口径；状态 = works.status 三态；结构进度 = N13 count_structure；最近活动 = 各作品 events 最新时间（无事件用创建时间）。
4. **零作品合法**：没有任何作品时输出 `no workspaces yet`（退出码 0），与 works list 空态一致。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更；纯 core 服务 + CLI + 测试。
- 复用既有查询（list_workspace_ids、Workspace、Decision/DraftVersion/Event/StructureNode 等），依赖方向 cli → core → store 不变；错误码沿用既有枚举。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 O1：聚合核心服务

### 做什么

- `core/overview.py`（新模块）：
  - dataclass `WorkspaceOverview`：workspace_id / title / genre / status（writing|completed|shelved）/ pending_count（int）/ structure（str，如 `2/5 章` 或 `-`）/ last_activity（datetime）/ created_at；
  - dataclass `WorkspaceOverviewReport`：overviews（list，按 last_activity 倒序，平局按 created_at 倒序、id 兜底）/ total（int）/ skipped（int）；
  - `build_overview(db) -> WorkspaceOverviewReport`：
    - 遍历全部 workspace（list_workspace_ids + global 注册表对齐，跳过无目录的孤儿注册项——或按 global 表为准，实现时与 works list 口径一致）；
    - pending_count：该作品 status=draft 的草稿数（decision pending 口径）；
    - structure：有结构节点时输出 `{completed_chapters}/{chapters} 章`，无结构时 `-`；
    - last_activity：events 最新 time（无事件用 workspace.created_at）；
    - 单作品查询异常：stderr 告警 `warning: overview skipped: {workspace_id}: {exc}`，计入 skipped 继续；
    - 零作品：overviews=[] total=0。
- tests：多作品聚合摘要（待拍板数、结构进度、状态、最近活动排序）、空态、单作品异常降级、跨作品不串、无结构 `-`、events 无时用 created_at。

### 做到什么程度

- 核心服务落地且有单测；既有 808 测试全绿（不接 CLI、不改既有命令输出）。

### 验收标准

- 单测覆盖上述全部路径；零作品与单作品异常路径正确。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（O2）、多作品卡点聚合（N19 一致性报告接入）、面板视图（N12）。

## 子阶段 O2：CLI 与端到端

### 做什么

- `cli/works.py`：新增 `works overview`：
  - 零作品输出 `no workspaces yet`（退出码 0）；
  - 每行 `[<状态标签>] <标题>（<体裁>）：待拍板 <N> · 进度 <2/5 章|-> · 最近 <时间戳>`，状态标签中文（创作中/已完成/搁置）；
  - 顺序与报告一致（最近活动倒序）；
  - 单作品跳过有 stderr 告警但命令仍退出码 0。
- tests：端到端「两部作品造不同状态 → works overview 顺序与摘要正确 → 无作品空态 → 单作品异常降级」；registry 补 works overview（若 SUBCOMMANDS 结构需要）。

### 做到什么程度

- 端到端可断言：老板一条命令看完全部编辑部状态；只读不阻塞。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 过滤/排序选项（后续按需）、面板视图（N12）、跨作品卡点报告（N19 接入）。

## 子阶段 O3：文档、全量回归与收口

### 做什么

- docs/usage.md 在「可见性（老板怎么看见编辑部）」节补「跨作品聚合（N10）」小节：works overview 输出格式、状态标签、排序口径、零作品空态与只读红线；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 808+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 图形面板聚合视图（N12 一并后置）、跨作品检索（N7 扩展）、自动轮询提醒。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。
- 后续单元（N8 / N9 / N11）在 N10 收口后按 backlog 顺序另拆。

## 状态

- 收口（2026-08-20）：O1（fb02c77）、O2（cedc0b6）、O2 审查修复（b3708d3）、O3（d395218）全部完成并独立审查收敛；全量 823 测试、smoke_m3、stress_m3 全绿；审查链归档 docs/reviews/20260820-M5N10O2-initial.md / 20260820-M5N10O2-fix.md / 20260820-M5N10O3.md。N10 正式收口。
