# M5/M6 实施真元文档（知识库重构 · N5 作品设定库）

## 总览

- **大阶段**：M6 知识库重构（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N5/N6/N7）。
- **当前只拆 N5**（作品设定库，P0 / G4，依赖 M3 全部）；N6 知识管家、N7 语义记忆检索只保留方向，不预拆细节（05a 纪律）。
- **N5 一句话**：作品设定（人物、关系、时间线、世界观）条目化、版本化、来源可溯——每一条设定知道从哪来、改过什么、现在是什么。
- **现状**：
  - 只有 plot_threads 承载叙事线索（伏笔/目标/钩子），没有独立的设定条目与版本历史；
  - 检索（search_memory / search_all_layers）覆盖档案/对话/意见/版本/笔记/线索，不含设定层；
  - Draft/DraftVersion 的版本化模式（版本号递增、reason 留痕、唯一约束）可照搬到设定上。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「建设定 → 修订 → 历史版本可溯（内容/原因/操作者逐版本可见）→ 检索命中 [设定] 层 → 跨作品不串」的端到端用例；不建设定不影响任何创作路径（红线 1）。

## 红线（继承 06 清单与 backlog，本阶段强制）

1. **沉淀不是前置**：设定库随创作自然沉淀，绝不要求「先建设定才能写/改/过稿」；无设定条目时既有全流程照常（回归测试锁定）。
2. **可溯不改写**：设定条目与版本只做记录，不自动改写正文、不绕过角色判断；revise 是显式动作，每条修订必须有原因与操作者。
3. **通用体裁**：设定条目对网文/同人/正统小说一律可用；kind 只是标签，不构成流程关卡，不按体裁特化。

## 地基影响评估（先评估再动工）

- 表结构增量：新增 `setting_entries` 与 `setting_versions` 两张表（沿用 Draft/DraftVersion 模式），走新 Alembic migration，纯追加，不动既有表。
- FTS 影子表不变：N5 的设定检索走 LIKE 子串匹配（search_memory / search_all_layers 的 [设定] 层），不新建 FTS 层（向量/FTS 深化留给 N7 评估）。
- 事件契约、错误码、依赖方向（cli → core → store）不变；错误路径沿用 NovelError(USAGE_ERROR / NOT_FOUND)。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 G1：数据模型、迁移与设定核心函数

### 做什么

- `store/models.py` 新增：
  - `SettingEntry`：id / workspace_id / kind（character|relation|timeline|world）/ name / content（当前内容）/ source（来源引用文本，默认「作者」）/ current_version（int，默认 0）/ created_at / updated_at；
  - `SettingVersion`：id / entry_id / version / content / reason / actor / created_at，UniqueConstraint(entry_id, version)。
- 新 Alembic migration（add table，纯追加；照 ede724222072 建表样式，down_revision 为当前 head `5b5bdeb4ed9d`）。
- `core/setting.py` 新建：
  - 常量：SETTING_KINDS（character/relation/timeline/world）与 KIND_LABELS（人物/关系/时间线/世界观）；
  - `add_setting(db, workspace_id, *, kind, name, content, source="作者") -> SettingEntry`：校验 kind、name 非空单行、content 非空；建 entry v1 并同时落 SettingVersion v1（reason="initial"、actor=source）；返回 entry；
  - `list_settings(db, workspace_id, kind=None)`：按 kind 过滤（可选），created_at 升序、id 兜底；
  - `get_setting(db, workspace_id, setting_id) -> SettingEntry`：未知报 NOT_FOUND；
  - `revise_setting(db, workspace_id, setting_id, *, content, reason, actor) -> SettingEntry`：校验 content/reason 非空；current_version+1，写 entry.content/updated_at 与 SettingVersion（version=新版本号、actor=actor）；返回 entry；
  - `list_setting_history(db, workspace_id, setting_id) -> list[SettingVersion]`：版本升序；未知 entry 报 NOT_FOUND。

### 做到什么程度

- 两表迁移、五个函数全部落地且有单测；既有 525 测试全绿；
- 覆盖：建条目 v1 双表落库、kind/name/content/reason 空值校验、单行校验、NOT_FOUND、修订版本递增与内容同步、历史升序、跨作品隔离。

### 验收标准

- 单测覆盖上述全部路径；迁移对全新库与已有作品库都安全（沿用旧库回填测试模式）。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI 与检索接入（G2）、设定自动注入记忆包/知识分发（N6）、陈旧识别（N6）、一致性核查（N19）、FTS/向量索引（N7）。

## 子阶段 G2：CLI 命令与检索接入

### 做什么

- 新增 `cli/setting.py`（新命令组 `setting`，注册进 app.py 的 _GROUP_LOADERS）：
  - `setting add <作品ID> --kind <人物|关系|时间线|世界观> --name <名称> --content <内容> [--source <来源>]`：输出 `added <设定ID> [人物] <名称> v1`；
  - `setting list <作品ID> [--kind <...>]`：输出每行 `设定ID [人物] <名称> v<N> <内容>`，空态输出提示；
  - `setting show <作品ID> <设定ID>`：输出名称、kind、当前版本、来源与当前内容；
  - `setting revise <作品ID> <设定ID> --content <内容> --reason <原因> [--actor <操作者>]`：输出 `revised <设定ID> <名称> v<N>`；
  - `setting history <作品ID> <设定ID>`：逐版本输出 `v<N> <actor> <reason> <内容>`；
  - 校验与退出码语义沿用既有模式（用法错误 2 / 业务错误 1）。
- `core/views.py` 的 `search_memory` 与 `search_all_layers` 各加 [设定] 层：对 SettingEntry.name / content 做 LIKE 子串匹配（沿用 _like_contains），输出 `[设定] {kind标签}：{name}——{snippet}（来源: {source} v{current_version}）`；按 updated_at 升序、id 兜底；FTS 可用与否不影响该层。
- tests：CLI 五命令、检索两路径的 [设定] 层、跨作品隔离、错误路径；test_cli_registry.py 的 SUBCOMMANDS 加 `"setting": ("add", "list", "show", "revise", "history")`。

### 做到什么程度

- 端到端可断言：add → revise → show/history 版本与来源可溯 → search 命中 [设定] → 跨作品不串；
- 既有 525 测试全绿（含无设定时创作全流程照常的回归断言）；smoke_m3 仍 SMOKE OK。

### 验收标准

- 端到端用例 + 错误路径（空值、未知 kind、未知设定、空历史）+ FTS/LIKE 两路径下 [设定] 层一致。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 设定自动注入记忆包与按角色分发（N6）、设定影响分析（N18）、一致性自动核查（N19）、图形面板（后置）。

## 子阶段 G3：文档、全量回归与收口

### 做什么

- docs/usage.md 新增「作品设定库（N5）」节：五条命令、kind 与版本语义、来源与修订留痕、检索 [设定] 层、红线（沉淀不是前置、不改写正文）；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 525+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 设定版本对比 diff（后续增量）、模板化设定（N26 再议）、面板可视化（后置）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N6 / N7 / N18 / N19）在 N5 收口后按 backlog 顺序另拆。

## 状态

- 立项（2026-08-19）：实施文档就绪，用户确认后拆包 G1。
- G1 完成（2026-08-19；commits 5bec3b6 / 2f0974b，全量 561 测试绿；两表迁移与五个核心函数 + 独立审查 actor 校验修复，审查链归档 docs/reviews/）。G2 待拆包。
- G2 完成（2026-08-19；commit 956a41e，全量 586 测试绿；setting 五命令 + 检索 [设定] 层 + source 校验补漏，独立审查无意见，审查链归档 docs/reviews/）。G3 待拆包。
