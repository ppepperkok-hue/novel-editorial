# M5 实施真元文档（知识库扩展 · N15 灵感素材库）

## 总览

- **大阶段**：M6 知识库扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N5 已收口，N15 为下一 P2 候选）。
- **N15 一句话**：灵感、素材、意象、片段随手存进作品库，创作时按需取用——灵感不丢、写作不干。
- **现状**：
  - N5 设定库已有版本化条目与来源可溯；N7 语义检索已有向量层；
  - 无「随手记」的轻量素材入口：作者的想法要么进对话，要么进设定库（太重）。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「add 三条不同 kind 且含关键词 → list 按 kind 过滤 / 按关键词命中 → show 原文与来源 → remove → list 消失 → events list 可见 created / removed 事件」；既有 1074 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **沉淀不是前置**：灵感库完全可选，不阻塞任何创作命令；不自动灌入写手记忆包（信息分层，作者显式取用，守 G4「最小充分信息」）。
2. **只读检索**：`list` / `show` 不落事件、不触发 proactive；`add` / `remove` 各落一条 SYSTEM 事件。
3. **检索口径可复现**：kind 精确匹配；keyword 对 content / source 做不区分大小写子串匹配；排序 `updated_at desc, id asc` 决胜；相同输入重复执行输出一致。
4. **可追溯**：每条灵感带 source（默认空）；remove 只删一条，事件 payload 含 inspiration_id 与 kind；失败不留半成品。
5. **体裁自适应与模板开放**：任意作品可用；零条目空态 `no inspirations`；kind 是开放标签不是封闭枚举（作者可自由命名）。

## 地基影响评估（先评估再动工）

- **新增表** `inspirations`（workspace 级）：id（String 32）、workspace_id（索引）、kind（String 20，默认「灵感」）、content（Text）、source（Text 默认 ""）、created_at、updated_at；新增 Alembic 迁移（down_revision = 当前 head）与 `store/models.py` 的 `Inspiration` 模型——属本单元立项范围。
- 新增 `core/inspiration.py` 服务 + `cli/inspiration.py` 命令组（`cli/app.py` 注册）。
- 无新依赖；依赖方向 cli → core → store 不变；不碰事件契约（复用 EventType.SYSTEM）。
- 若实现中发现必须破坏性改既有表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：核心服务与迁移

### 做什么

- Alembic 迁移（`migrations/versions/*_add_inspirations.py`）：建 `inspirations` 表 + workspace_id 索引；`store/models.py` 加 `Inspiration` 模型（字段如上）。
- `core/inspiration.py`：
  - `add_inspiration(db, workspace_id, *, content, kind="灵感", source="") -> Inspiration`：content / kind 去空白后非空，否则 NovelError(USAGE_ERROR)；复用 `get_workspace_or_raise`；落 SYSTEM 事件 `inspiration_created`（payload：`{"kind": "inspiration_created", "inspiration_id": ..., "inspiration_kind": ...}`，沿用全库 SYSTEM 事件「payload.kind 即事件子类型」惯例）；返回行；
  - `list_inspirations(db, workspace_id, *, kind=None, keyword=None) -> list[Inspiration]`：kind 精确过滤；keyword 对 content / source 不区分大小写子串匹配；排序 `updated_at desc, id asc`；
  - `get_inspiration(db, workspace_id, inspiration_id) -> Inspiration`：不存在 NovelError(NOT_FOUND)；
  - `remove_inspiration(db, workspace_id, inspiration_id) -> Inspiration`：先 get 后删；落 SYSTEM 事件 `inspiration_removed`（payload：`{"kind": "inspiration_removed", "inspiration_id": ..., "inspiration_kind": ...}`）；返回被删行。
- tests（`tests/test_inspiration.py`）：add / list 过滤与排序 / keyword 命中（含大小写） / show / remove / 事件流（created/removed 可见、list/show 不新增事件）/ 空态 / 空内容 USAGE_ERROR / 作品与灵感不存在 NOT_FOUND。

### 做到什么程度

- 灵感库增删查可复现、事件留痕；CLI 不接。

### 验收标准

- 单测覆盖上述全部路径；迁移可往返（upgrade / downgrade）。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（S2）、文档（S3）、灵感入语义检索向量层（N7 联动）、标签体系、自动归档。

## 子阶段 S2：CLI 与端到端

### 做什么

- `cli/inspiration.py`（`cli/app.py` 注册 inspiration 组）：
  - `inspiration add <作品ID> --content <内容> [--kind 灵感] [--source ""]` → `added <灵感ID> [<kind>] <内容>`（内容走选项，避免 `-` 开头文本被 Click 误判为选项，与 `setting add` 惯例一致）；
  - `inspiration list <作品ID> [--kind] [--keyword]` → 每行 `<灵感ID> [<kind>] <内容>`；空态 `no inspirations`；
  - `inspiration show <作品ID> <灵感ID>` → `kind:` / `content:` / `source:`（source 空显示 `(empty)`）；
  - `inspiration remove <作品ID> <灵感ID>` → `removed <灵感ID> [<kind>]`；
  - 退出码：作品 / 灵感不存在 1；空内容 2。
- tests：registry 补 inspiration 组；端到端「add 三条 → list 过滤 / 关键词 → show → remove → list 消失 → events list 可见」；退出码路径。

### 做到什么程度

- 作者一条命令随手存、随手取；零配置、零前置。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 灵感入向量检索（N7 联动）、批量导入、标签 / 分类管理、自动整理。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- 修复 S2 独立审查两个 P3（允许触碰 cli/inspiration.py 与 tests/test_inspiration_cli.py）：
  - `inspiration add` 的 content 从位置参数改为 `--content` 选项（`- 破折号` 等文本可正常存入）；
  - `tests/test_inspiration_cli.py` 的 `_create_workspace` 改用正则解析作品 id（与 test_cli_registry 一致），不再依赖 `split()[2]`。
- usage.md 增「灵感素材库（N15）」小节（放在「作品设定库（N5）」小节附近）：四条命令、kind 开放标签语义、检索口径、只读 / 事件红线、mock 实跑示例。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260822-M5N15S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 1074+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 向量检索联动（N7）、批量导入导出、灵感自动沉淀、标签体系。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权低价窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-22）：实施文档就绪，用户授权低价窗口内自主推进，拆包 S1。
