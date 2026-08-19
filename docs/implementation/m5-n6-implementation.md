# M6 实施真元文档（知识库重构 · N6 知识管家）

## 总览

- **大阶段**：M6 知识库重构（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N5/N6/N7）。
- **当前只拆 N6**（知识管家，P0 / G4，依赖 N5）；N7 语义记忆检索只保留方向，不预拆细节（05a 纪律）。
- **N6 一句话**：设定变更自动分发到相关层并在后续创作中生效——写手记忆包与编辑视图永远拿到当前版本，修订在事件流留痕；陈旧/矛盾设定被识别（check 报告），向下分发闭环不靠人肉。
- **现状**：
  - N5 已交付设定条目化/版本化/来源可溯，但设定尚未注入记忆包与编辑视图，检索只按需命中；
  - build_memory_pack 有作品档案/风格/章纲/私有记忆/悬置线索，没有设定段；
  - 修订（revise_setting）只写库，事件流不可见。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「建设定 → 修订 → 记忆包/编辑视图自动显示当前版本 → 事件流可见修订 → setting check 报告同名矛盾候选与已修订条目」的端到端用例；分发永远用当前版本，不因陈旧版本污染创作上下文。

## 红线（继承 06 清单与 backlog，本阶段强制）

1. **沉淀不是前置**：分发只做注入与提示，绝不要求「先建设定才能写/改/过稿」；无设定条目时记忆包与视图照常（回归测试锁定）。
2. **只报告不改写**：check 只输出报告供作者判断，不自动改设定、不改正文、不绕过角色判断。
3. **分发用当前版本**：记忆包/编辑视图/检索一律读 current_version 的内容，绝不分发历史版本；旧版本只留在 history 里可溯。
4. **通用体裁**：分发与 check 对网文/同人/正统小说一律可用，不按体裁特化。

## 地基影响评估（先评估再动工）

- 无表结构变更、无迁移：分发读既有 setting_entries，修订事件复用既有 events 表与 EventType.SYSTEM（payload 带 kind="setting_revised"，不新增事件枚举）。
- 事件契约、错误码、依赖方向（cli → core → store）不变；错误路径沿用 NovelError(USAGE_ERROR / NOT_FOUND)。
- 若实现中发现必须改表结构 / 事件契约 / 错误码，先停下回报，不硬做。

## 子阶段 H1：分发与修订事件留痕

### 做什么

- `core/draft.py` 的 `build_memory_pack` 增加「设定：」段（放在私有记忆之后、悬置线索之前）：
  - 行格式 `- [人物] 沈夜 v2 当前内容（来源: 作者）`；
  - 顺序：kind 固定序（人物→关系→时间线→世界观），同 kind 按 updated_at 升序、id 兜底；
  - 无设定条目时整段不出现。
- `core/views.py` 的 `build_editor_view`（总编/责编视图）同样增加「设定：」段（同格式），让相关层都拿到当前版本。
- `core/setting.py` 的 `revise_setting` 在版本落库后追加一条 SYSTEM 事件（复用 record_event）：payload `{"kind": "setting_revised", "setting_id": ..., "name": ..., "version": 新版本, "actor": ..., "reason": ...}`；事件写入失败只告警（stderr），不回滚修订。
- tests：记忆包与编辑视图含当前版本设定、无设定时无段、修订后立即反映、事件流可断言、事件失败不阻塞修订、跨作品隔离。

### 做到什么程度

- 分发闭环：add → revise → memory pack / editor view 自动显示 v2 当前内容；events list 能看到 setting_revised；
- 既有 586 测试全绿，smoke_m3 仍 SMOKE OK。

### 验收标准

- 端到端：修订后 pack/view 输出与事件 payload 可断言；事件写入失败时修订成功、stderr 有 warning。

### 验证方式

pytest（新增用例）+ smoke_m3。

### 暂不做

- check 命令（H2）、按角色裁剪分发（后续增量）、设定影响分析（N18）。

## 子阶段 H2：陈旧/矛盾识别与 setting check

### 做什么

- `core/setting.py` 新增 `check_settings(db, workspace_id) -> str`：
  - 统计：总条目数、已修订条目数（current_version > 1）；
  - 陈旧提示：列出已修订条目 `- 沈夜（人物）v2 当前内容（来源: 作者）—— 已修订，旧版本见 history`；
  - 矛盾候选：同名条目（任意 kind）分组列出 `- 「沈夜」：人物 v1 与 人物 v2 —— 同名条目，请确认是否矛盾`；
  - 无任何候选时输出 `settings: N entries (M revised)；同名冲突：无`。
- `cli/setting.py` 新增 `setting check <作品ID>`：输出 check_settings 结果，退出码沿用业务语义。
- tests：统计、已修订列表、同名冲突分组、空态、跨作品隔离、registry 补 `check`。

### 做到什么程度

- check 报告确定性可断言；同名条目即使不同 kind 也能被识别为候选；
- 既有 586 测试全绿，smoke_m3 仍 SMOKE OK。

### 验收标准

- 单测覆盖统计/陈旧/矛盾/空态；`setting check` 端到端输出与报告一致。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3。

### 暂不做

- 语义矛盾检测（依赖向量检索 N7 或一致性核查 N19）、设定影响分析（N18）、自动修正（红线 2）。

## 子阶段 H3：文档、全量回归与收口

### 做什么

- docs/usage.md 新增「知识管家（N6）」节：分发语义（记忆包/编辑视图/检索永远当前版本）、修订事件留痕、setting check 命令与陈旧/矛盾候选语义、红线（沉淀不是前置、只报告不改写）；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 586+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 按角色裁剪设定分发、模板化设定（N26 再议）、面板可视化（后置）、语义矛盾检测（N7/N19）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N7 / N18 / N19）在 N6 收口后按 backlog 顺序另拆。

## 状态

- 立项（2026-08-19）：实施文档就绪，待用户确认后拆包 H1。
