# M5 实施真元文档（老板视角与开源 · N11 示例编辑部与剧本）

## 总览

- **大阶段**：M8 老板视角与开源（backlog 见 docs/project-plan/06-new-capability-backlog.md；N10 已收口，N11 为下一候选，N12 用户明确后置）。
- **N11 一句话**：新作者 clone 下来不配 key，一条命令就有一个「活的」编辑部——预置的作品、班子、设定、大纲、对话、待拍板草稿、伏笔与记忆，30 分钟感受到价值。
- **现状**：
  - `demo` 是动态端到端演示：建《演示之书》→ talk → 生成草稿 → 质量门 → 拍板，依赖 LLM（mock 时回复固定），跑完即止，没有预置内容；
  - 各能力（设定库 N5、知识管家 N6、语义检索 N7、质量门 N8/N9、结构 N13、多写手 N14、记忆衰减 N17、影响分析 N18、聚合视图 N10）已收口，但没有「开箱即有的示例作品」入口。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「不配 key → 一条命令生成示例编辑部 → works overview / events list / inspect / setting list / memory notes / decision pending / talk list / behavior timeline 均有内容 → 重复执行生成新示例且旧数据不动」；既有 881 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **不配 key 可跑**：示例生成全程不调用 LLM（mock 语义），预置内容确定性写入，重复执行结果可复现。
2. **不污染用户数据**：示例只新建一个独立 workspace（标题可辨识，如「示例·雨夜车站」），绝不修改/删除既有作品与配置；示例不是任何创作流程的前置，`init` / `demo` / 既有命令行为不变。
3. **可重复、可清理**：重复执行创建新的示例 workspace（不覆盖旧的，不抛错）；清理 = 删除对应数据目录（README/输出提示说明），不引入破坏性命令。
4. **内容真实可体验**：示例覆盖分层信息（作品档案 / 风格锚点 / 设定库 / 大纲 / 结构 / 对话 / 草稿 / 伏笔 / 记忆 / 行为时间线 / 事件流），让「老板视角」各命令开箱即有内容可看、可继续操作（拍板 / 修订 / 讨论）。
5. **确定性优先**：示例文本与结构固定；生成的 id 随运行变化但内容一致，测试断言用内容与计数，不断言 id。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更；新增 core 模块 + 顶层 CLI 命令 + 测试。
- 复用既有 core 函数（create_workspace / style / setting / outline / structure / chat / plot / memory / behavior / draft 直写 + 事件），依赖方向 cli → core → store 不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 R1：示例种子服务

### 做什么

- `core/example.py`（新模块）：
  - `ExampleResult`：workspace_id / title / genre / 预置计数（settings / outline / structure_nodes / messages / drafts / threads / notes / behavior_entries / events）；
  - `seed_example_workspace(db) -> ExampleResult`：
    - `create_workspace(db, title="示例·雨夜车站", genre="悬疑", description=...)`；
    - 风格锚点（平实克制短句 + 禁忌词）；
    - 设定库 2–3 条（人物 / 时间线 / 世界观，复用 setting 服务）；
    - 大纲 v1（复用 outline 服务）；
    - 结构：一卷三章（第一章 completed，其余 writing，复用 structure 服务）；
    - 对话历史 2–3 条（作者发起 + 总编/责编回应，复用 chat 服务，含至少一条主动发言语义）；
    - 草稿：第一章 v1（正文为预置文本，状态 draft 待拍板——直接写 Draft/DraftVersion 并记 DRAFT_CREATED / quality_gate.passed / decision.requested 事件，不调 LLM）；
    - 伏笔线索 1–2 条（复用 plot 服务）；
    - 写手记忆笔记 1–2 条（复用 memory 服务）；
    - 行为时间线 1–2 条（复用 behavior 服务）；
    - 作品状态保持 writing；结构进度 1/3 章；
    - 不修改任何既有 workspace / 配置。
- tests（tests/test_example.py）：生成后各层计数与内容断言、事件流非空、works overview 行存在、不依赖 LLM（无 key 环境）、重复生成两个不同 id 且旧 workspace 数据不变、既有 881 测试不回归。
- 示例文本常量放模块内（参照 DEFAULT_BAND 的既有模式），不新增资源文件系统。

### 做到什么程度

- 一条核心函数把「活的编辑部」造出来，任何已有查询命令都能看到内容；CLI 不接。

### 验收标准

- R1 单测覆盖上述全部路径；mock 下确定性强。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（R2）、README/usage 文档（R3）、N26 模板化（另拆）。

## 子阶段 R2：CLI 与端到端

### 做什么

- `cli/app.py` 新增顶层命令 `example`（帮助文案：生成示例编辑部与示例作品）：
  - 调用 seed_example_workspace；
  - 输出：`created example workspace <id>: 示例·雨夜车站` + 一行体验指引（如 `Run works overview / events list <id> / decision pending <id> to explore`）；
  - 不配 key 可跑；重复执行每次生成新 workspace；
  - 不改变 init / demo / 其他命令行为。
- tests：端到端（runner 无 key → example → 输出 id → 各查询命令有内容 → 重复 example 两个 id、旧数据不动）；registry 顶层命令补 example。

### 做到什么程度

- 新作者一条命令进入可体验状态。

### 验收标准

- 端到端用例 + 幂等/隔离；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 示例清理命令（删除 workspace 是破坏性能力，未授权；README 提示手动删目录）、模板选择（N26）。

## 子阶段 R3：文档、全量回归与收口

### 做什么

- README「快速开始」补 `uv run novel-editorial example` 体验路径（30 分钟剧本：生成 → works overview / events / inspect / decision pending 看状态 → talk / decision 继续操作），usage.md 补对应小节（说明与 demo 的区别、不配 key、重复生成语义、手动清理方式、不污染用户数据）；
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260820-M5N11R1 / R2 / R3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 881+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 图形面板（N12，用户后置）、示例模板市场（N26）、一键清理命令。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-20）：实施文档就绪，用户授权低价窗口内自主推进，拆包 R1。
