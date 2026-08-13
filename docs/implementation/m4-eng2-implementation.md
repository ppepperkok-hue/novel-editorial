# M4-ENG-2 实施真元文档（瓶颈 2：检索性能）

## 总览

- **大阶段**：M4 工程瓶颈优化。瓶颈 2 = `inspect` / `memory search` 在 50 万字量级下的检索基线 ~1.4s（m3-closeout.md 归档：检索中位 ~1.4s，阈值 <10s）。
- **依赖顺序**：无外部依赖；改动集中在 `src/novel_editorial/core/views.py`（search_memory / search_all_layers）与对应测试。
- **基底（不可随意翻）**：技术栈、src 目录结构、数据库表设计（Alembic 迁移链）、事件契约、错误码、依赖方向。**方案 B（FTS5 虚拟表）涉及表设计扩展，已由用户 2026-08-14 批准 A+B 一起实施。**
- **验收总门**：验证四连全绿（pytest / ruff / pyright / 宪法）；CLI 冒烟；压力脚本 scripts/stress_m3.py 全项通过且检索指标改善；无越界实现；完成即停，回报三问。

## 现状根因（2026-08-14 实测修正）

`search_memory` 与 `search_all_layers` 都是：

1. 把作品内整表载入 Python（Message / Review / DraftVersion / AgentMemory / Decision / PlotThread 全量对象）；
2. 逐条 `needle in value.lower()` 子串匹配；
3. 命中才生成片段行。

50 万字正文量级下，全量载入 + 逐条 lower 是 ~1.4s 的主因，与命中多少无关。

**实测修正（M4-ENG-2-A 完成后）**：检索函数本体只占 5~15ms；`novel-editorial version` 这类零逻辑命令也要 ~1.4s。墙钟大头是 CLI 启动导入链：`import cli.app` 约 1.35s，其中 openai 约 0.9s、alembic（经 store.db）约 0.5s。因此"全量载入 + 逐条 lower"不是 CLI 墙钟 1.4s 的主因；方案 A 仍值得做（函数级提速 + 语义不变），但要让 CLI 检索墙钟 <1s，必须优化启动导入。

## 方案评估

### 方案 A（推荐，先做）：SQL 层 LIKE 过滤 + 命中行按需加载

- 把匹配下沉到 SQL：`LOWER(col) LIKE '%' || ? || '%'`，只 SELECT 命中行（或先取主键再按需加载 content）。
- 语义完全不变：仍是不区分大小写的子串命中，中英文都一致。
- 优点：改动集中在 views.py + 测试；不涉及表结构、不引入迁移、无新增依赖；风险最低。
- 预期：50 万字量级从 ~1.4s 降到数百 ms 级（不用索引，仍是扫描，但省掉对象加载与 Python 逐条 lower；瓶颈 2 的目标是 <1s）。
- 暂不做：分页、排序评分、命中高亮（片段已有）。

### 方案 B（第二阶段，需另行批准）：FTS5 trigram 全文索引

- 已实测环境：SQLite 3.45.1，ENABLE_FTS5=True，trigram tokenizer 可用。
- 行为：3 字符及以上关键词走 FTS MATCH 索引（命中在毫秒级）；2 字符关键词 trigram 不命中，需回退方案 A 的 LIKE。
- 优点：性能上限最高，检索从秒级到毫秒级。
- 代价：新增 FTS5 虚拟表 + 增量同步（触发器或应用层写入钩子）+ Alembic 迁移；属于表设计扩展，按变更纪律需先评估再实现。
- 暂不做：FTS5 辅助表对结果排序/合并分层的复杂化；先保证"同一关键词两种路径结果一致"的测试守卫。

### 方案 C（已记录为后置候选，不纳入本阶段）：向量 / 语义检索

- 引入外部嵌入依赖与 API 成本，语义是"意思相近"而非"子串命中"，与当前 F18 行为契约不同。
- 定位：后续"知识库/记忆检索"增量功能时再立项，不解决本瓶颈；增量性能评估见正文，已登记到 docs/project-plan/04-feature-breakdown.md 后置候选。

## 子阶段划分（2026-08-14 用户批准：A+B 一起实施）

### A. 检索下沉（方案 A）

- 做什么：
  1. `search_memory` / `search_all_layers` 的每个文本层改为 SQL `LOWER(col) LIKE '%'||?||'%'` 过滤，只载入命中行；涉及字段：档案（workspaces.title / genre / description）、对话（Message.content / actor）、意见（Review.content / actor）、版本（DraftVersion.content + Draft.title 标题命中）、笔记（AgentMemory.content）、决策（Decision.action / actor / content）、线索（PlotThread.content / kind / status）、风格（StyleAnchor.description / forbidden_words）。
  2. 保持现有输出格式与顺序（按 created_at, id 升序）与片段/来源格式完全不变。
- 做到什么程度：inspect / memory search 结果与优化前逐字节一致（同一数据、同一关键词）；50 万字量级压力下检索 <1s。
- 涉及功能：F18 / U19 检索；单元 M4-ENG-2-A。
- 验收标准：既有测试全绿（237+）；新增或调整测试覆盖"命中行加载"与"无命中"；scripts/stress_m3.py 检索项 <1s（归档新基线）。
- 验证方式：pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3。
- 暂不做：索引、FTS、向量（见方案 B/C）。
- 影响评估（涉及基底）：不改表结构、不迁移；只改 core/views.py 查询方式，符合依赖方向。
- 状态：已完成（c4d7f6c，2026-08-14）。241 passed、ruff/pyright/宪法 OK、smoke OK、stress OK；新旧输出 8 组逐字节一致；函数级耗时 ~8~39ms → ~4~9ms。

### A2. CLI 启动导入优化（新增，让检索墙钟 <1s 的关键）

- 做什么：把启动导入链中的重依赖延迟化——
  1. `llm/client.py` 的 `openai` 顶层导入改为延迟导入（进入 OpenAICompatClient 构造时再 import）；
  2. `store/db.py` 的 alembic 依赖延迟化（仅在迁移/升级路径 import）；
  3. CLI 命令组按需加载（typer 支持回调内 add_typer 或惰性注册，先评估最简可行方案）；
  4. 保持现有 CLI 行为、退出码、输出完全不变。
- 做到什么程度：`novel-editorial version` / `memory search` / `inspect` 墙钟显著下降；50 万字量级检索 CLI 墙钟 <1s；全量验证全绿。
- 涉及功能：瓶颈 2 性能；单元 M4-ENG-2-A2。
- 验收标准：版本命令与检索命令墙钟对比（压测脚本记录）；241+ 测试全绿。
- 验证方式：pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3。
- 暂不做：进程常驻 / daemon 化、入口脚本瘦身、面板。
- 影响评估（涉及基底）：不改表结构、不迁移、不改依赖方向；只调整导入时机，属 cli/llm/store 模块内改动。
- 状态：已批准（2026-08-14），待派包。

### B. FTS5 全文索引（方案 B，待另行批准）

- 做什么：为正文层（对话 / 版本 / 意见 / 笔记 / 线索）建 FTS5 trigram 虚拟表；3 字符及以上关键词走 MATCH，2 字符回退 LIKE；迁移建表 + 回填 + 增量同步。
- 做到什么程度：3 字符以上关键词命中毫秒级；与 LIKE 结果一致（测试守卫）。
- 涉及功能：同上。
- 验收标准：双路径结果一致性测试（同一数据、同一关键词，FTS 路径与 LIKE 路径逐行一致）；全量验证全绿；
  in-process 函数级 3 字符以上关键词 FTS 与 LIKE 耗时对比（记录真实数据，不硬性 <200ms——CLI 墙钟由
  启动导入主导，函数级在 50 万字量级本就个位数 ms；FTS 收益体现在更大数据与进程常驻场景）。
- 暂不做：向量、评分排序、跨作品索引。
- 状态：**已批准按原计划实施（2026-08-14 用户决定 A2+B 都上）**。已知 CLI 墙钟收益有限，收益点主要在进程常驻场景；实施时保留双路径一致性守卫与 2 字符回退。

### B0. M4-ENG-2 收口

- 收口时做阶段审查（M4-ENG-2 全链总审）：A / A2 / B 三个子阶段全部完成后，派独立审查 CLI 做总审，归档审查报告，更新基线文档（m4-eng2-closeout.md），收口即推。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 涉及基底（技术栈 / 目录 / 表设计 / 事件契约 / 错误码 / 依赖方向）的改动：先停下评估影响，给方案再实现。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
