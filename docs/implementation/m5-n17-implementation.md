# M5 实施真元文档（自然行为与自由意志 · N17 记忆衰减与归档）

## 总览

- **大阶段**：M5 自然行为与自由意志（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N1/N2/N3/N4/N16/N17）。
- **当前只拆 N17**（记忆衰减与归档，P1 / G3 + G4，依赖 N3）。
- **N17 一句话**：伙伴私有记忆随时间自然衰减、旧记忆归档，让记忆像人一样有轻重，而不是无限堆叠；衰减只降权重、归档可逆、绝不自动删除。
- **现状**：
  - `agent_memories` 只有 workspace_id / agent_id / content / created_at，没有轻重、没有归档状态；
  - 私有笔记在检索（views.search_memory / search_all_layers）里按 created_at 排序，在写作记忆包（draft.build_memory_pack）里原样注入；
  - M2 当时明确「暂不做：记忆衰减」（docs/implementation/m2-implementation.md 子阶段 C），本单元补齐这一块。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「写入私有笔记 → 时间流逝发生衰减 → 弱记忆进入归档候选 → 归档后默认检索/记忆包不可见但可查可恢复 → 恢复后重新可见」的端到端用例；衰减不删除内容、归档可逆、衰减不阻塞任何创作或检索路径。

## 红线（本阶段强制）

1. **衰减是权重，不是删除**：衰减只降低 strength、改变排序与默认可见性，绝不自动删除内容；`memory delete` 仍是唯一真正删除的通道，行为不变。
2. **归档可逆且留痕**：归档只置 archived_at（状态留痕），内容原样保留；`memory restore` 随时恢复，无数据损失。
3. **衰减不阻塞**：检索与记忆包只按强度排序、默认排除归档，永不因强度低而阻断注入或检索；不设「必须保鲜才能用」之类的强制节点。
4. **权限不扩权**：笔记内容写入的既有权限（作者只读、伙伴只写自己）不变；衰减/归档/恢复/保鲜是本地状态管理命令，不新增权限细分（本地单人工具）。

## 地基影响评估（先评估再动工）

- 表结构增量：`agent_memories` 新增三列——`strength`（int，默认 100，非空）、`last_accessed_at`（datetime，默认创建时间，非空）、`archived_at`（datetime，可空）。走新 Alembic migration，纯追加、带默认值，对既有行安全；不删改既有列。
- FTS 影子表（agent_memory_fts）仍只索引 content，不随新列变化；事件契约、错误码、依赖方向（cli → core → store）不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 F1：衰减模型、归档状态与数据迁移

### 做什么

- `store/models.py`：AgentMemory 新增 strength / last_accessed_at / archived_at 三列（含默认值）；新增 Alembic migration（add column，既有行回填默认值）。
- `core/config.py`：Settings 新增 `memory_decay_per_day: int = 5`、`memory_rehearsal_boost: int = 25`、`memory_archive_threshold: int = 20`；支持 `NOVEL_MEMORY_DECAY_PER_DAY` / `NOVEL_MEMORY_REHEARSAL_BOOST` / `NOVEL_MEMORY_ARCHIVE_THRESHOLD` 与 config.toml `[defaults]` 覆盖；非负校验，阈值不超过 100，非法报 CONFIG_ERROR。
- `core/memory.py`：
  - `effective_strength(note, now)`：`max(0, min(100, note.strength - decay_per_day * 距 last_accessed_at 的整天数))`，纯计算、不落库；
  - `apply_memory_decay(db, workspace_id, now=None)`：对活跃笔记按 last_accessed_at 折算并写回 strength，同日重复执行 strength 不变（幂等），返回受影响笔记；
  - `list_archive_candidates(db, workspace_id, now=None)`：活跃笔记中 effective_strength ≤ 阈值的列表；
  - `rehearse_memory_note(db, workspace_id, memory_id, now=None)`：strength = min(100, strength + boost)、last_accessed_at = now；已归档笔记报 USAGE_ERROR，未知笔记报 NOT_FOUND；
  - `archive_memory_notes(db, workspace_id, note_ids=None, *, candidates=False, now=None)`：显式 ids 直接归档（不限强度，供作者整理）；candidates=True 归档全部阈值候选；置 archived_at = now；
  - `restore_memory_notes(db, workspace_id, note_ids, now=None)`：清除 archived_at，strength / last_accessed_at 保持原值（恢复即回到活跃，不额外加权）；
  - `list_memory_notes(db, workspace_id, agent_id=None, include_archived=False)`：默认排除已归档，按 strength 降序、created_at 升序（确定性）。

### 做到什么程度

- 三列迁移、配置、六个函数全部落地且有单测；既有 465 测试全绿（含 memory pack 既有断言不破）；
- 衰减计算覆盖边界（同日、跨天、衰减到 0、strength 上限）、幂等、候选阈值、rehearse 上限、归档/恢复可逆、list 默认排除与排序。

### 验收标准

- 单测覆盖上述全部路径；配置三来源（默认 / TOML / 环境变量）与非法值报错。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 检索与记忆包接入（F2）、CLI 命令（F2）、自动背景衰减调度、概率性遗忘、记忆合并去重（N6/N7 后续）。

## 子阶段 F2：检索、记忆包与 CLI 接入

### 做什么

- `core/views.py` 的 `search_memory` 与 `search_all_layers`：
  - 笔记命中默认排除已归档（archived_at IS NULL），排序改为 strength 降序、created_at 升序（用 effective_strength 计算，不落库）；
  - 每条命中的笔记用 rehearse 做「检索即想起」保鲜（安全封装：失败只告警，检索结果不受影响）。
- `core/draft.py` 的 `build_memory_pack` 私有记忆段：排除已归档，按 strength 降序注入。
- `cli/memory.py` 新增命令：
  - `memory decay <作品ID>`：应用衰减并逐条输出强度变化；无变化时输出提示；
  - `memory remember <作品ID> <笔记ID>`：保鲜并输出新强度；
  - `memory archive <作品ID> [笔记ID...] [--candidates]`：归档显式目标或全部阈值候选，输出归档条数；无目标且无候选时报用法错误；
  - `memory restore <作品ID> <笔记ID...>`：恢复并输出条数；
  - `memory notes` 增加 `--include-archived`：默认排除归档，输出带强度与【归档】标记。

### 做到什么程度

- 端到端可断言：写入 → 衰减 → 候选 → 归档 → 默认检索 / notes / memory pack 不可见、`--include-archived` 可见 → restore 恢复可见；
- 检索保鲜生效（搜索命中后 strength 上升、上限 100）、保鲜失败不影响检索结果；
- FTS 与 LIKE 两条检索路径行为一致；既有 465 测试全绿，smoke_m3 仍 SMOKE OK。

### 验收标准

- 端到端用例 + 失败路径（monkeypatch 保鲜写入抛错，检索结果不变）+ 归档笔记在检索与记忆包中不可见但可恢复。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3（stress 的 memory search 阈值不回归）。

### 暂不做

- 检索自动摘要、记忆合并去重、印象/关系数值化（N3 已明确不做数值权重）、后台定时衰减调度器。

## 子阶段 F3：文档、全量回归与收口

### 做什么

- docs/usage.md 新增「记忆衰减与归档（N17）」节：衰减模型与三项配置（NOVEL_MEMORY_* / config.toml）、decay / remember / archive / restore / notes --include-archived 命令、归档在检索与记忆包的语义、可逆说明、红线（不删除、不阻塞）；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 465+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板可视化（后置）；记忆统计报告（N10 时再议）；N5/N6 设定库与知识管家（N17 收口后按 backlog 顺序另立项）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N5 / N6 / N13）在 N17 收口后按 backlog 顺序另拆。

## 状态

- 立项（2026-08-18）：实施文档就绪，用户确认后拆包 F1。
- F1 完成（2026-08-18；commits 169be08 / 43ed147，全量 506 测试绿；衰减模型、归档状态与数据迁移 + 独立审查两条 P3 修复，审查链归档 docs/reviews/）。F2 待拆包。
