# M6 实施真元文档（知识库重构 · N7 语义记忆检索）

## 总览

- **大阶段**：M6 知识库重构（backlog 见 docs/project-plan/06-new-capability-backlog.md，单元 N5/N6/N7）。
- **当前只拆 N7**（语义记忆检索，P1 / G4，依赖 N5 / 检索层）；已评估为**架构级增量**：引入嵌入抽象、索引表与增量一致性，独立立项、风险前置。
- **N7 一句话**：检索按「意思相近」联想记忆片段——私有笔记与设定条目除了关键词命中，还能按语义相似被想起；索引随写入/修订/删除增量同步，后端不可用时优雅降级，绝不阻塞创作。
- **现状**：
  - search_memory / search_all_layers 全部是 LIKE/FTS 子串匹配，只认字面命中；
  - AgentMemory 与 SettingEntry 有内容/版本/归档语义，但没有向量索引；
  - 项目已有统一 LLM 客户端（OpenAI 兼容，mock 模式确定性），可作为嵌入 API 的可选后端底座。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条「写入两条意思相近但无共同关键词的笔记 → 语义检索命中 → 删除后不再命中 → 修订设定后向量同步 → 后端不可用时关键词检索照常」的端到端用例；既有关键词检索行为不回退。

## 红线（本阶段强制）

1. **检索不阻塞**：向量缺失、后端不可用、索引未就绪时一律优雅降级到关键词检索（fail-closed），不报错、不打断既有命令；语义结果只是增强。
2. **增量一致**：笔记增/删/改、设定增/改时索引同事务或紧随事务同步；`memory reindex` 可重建补齐存量；归档笔记默认不参与语义命中（与关键词检索一致）。
3. **配置驱动、默认离线**：`NOVEL_EMBEDDING_BACKEND=local`（默认）时零外部依赖、确定性、可离线复现；`api` 后端显式配置才启用（复用 NOVEL_LLM_BASE_URL / API key，模型可配），文档如实说明两档能力差异。
4. **不破坏既有契约**：`memory search` 默认输出不变；语义命中只在显式开关（`--semantic`）下出现，行格式沿用 [笔记]/[设定] 引用式并加相似度后缀。

## 地基影响评估（先评估再动工）

- 表结构增量：新增 `memory_embeddings` 表（workspace_id / layer / source_id / vector(Text JSON) / dim / updated_at，UniqueConstraint(layer, source_id)），走新 Alembic migration，纯追加。
- 新增模块：`llm/embeddings.py`（EmbeddingClient 抽象 + LocalNGramEmbedder + OpenAICompatEmbedder）、`core/retrieval.py`（索引同步与语义检索服务）。
- 配置增量：Settings 新增 embedding_backend（local|api，默认 local）、embedding_model（local 后端可空；api 后端必须显式配置，空则报 CONFIG_ERROR）、embedding_dim（默认 256）、embedding_top_k（默认 5）；NOVEL_EMBEDDING_* 环境变量与 config.toml [defaults] 同名键。
- 事件契约、错误码、依赖方向（cli → core → store/llm/quality）不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 能力边界（如实说明）

- 默认 local 后端 = 字符 n-gram 哈希向量 + 余弦相似度：能捕捉词序变化、部分重叠与字形近义（如「雨夜回乡」命中「雨夜归乡」），是**字面近义近似**，不是语言模型级语义；
- api 后端（显式配置、在线、可付费）才是真语义嵌入；两档共用同一索引表与检索服务，换后端只需重建索引（reindex）；
- v1 索引层：AgentMemory（私有笔记，当前内容）与 SettingEntry（设定，current_version 内容）；对话/意见/正文版本等层暂不索引（后续按需扩层）。

## 子阶段 I1：嵌入抽象、索引表与增量同步

### 做什么

- `llm/embeddings.py`：
  - `EmbeddingClient` 抽象：`embed(text: str) -> list[float]`；
  - `LocalNGramEmbedder(dim)`：字符 n-gram（n=1..3）哈希桶向量 + L2 归一化，确定性、无依赖；
  - `OpenAICompatEmbedder`：调 OpenAI 兼容 /embeddings（复用 base_url / api_key / 现有 openai SDK），失败抛 LLMError；
  - `build_embedding_client(settings)`：按 embedding_backend 分派。
- `core/config.py`：新增 embedding_backend / embedding_model / embedding_dim / embedding_top_k 四项配置（默认 local / "" / 256 / 5，校验：backend 只允许 local|api，dim 为正整数 32–4096，top_k 为正整数 1–50）。
- `store/models.py` + 新 Alembic migration：`memory_embeddings`（workspace_id / layer / source_id / vector / dim / updated_at，UniqueConstraint(layer, source_id)，down_revision 为当前 head `92a0cb3a3bb1`，幂等建表照既有风格）。
- `core/retrieval.py`：
  - `upsert_embedding(db, workspace_id, *, layer, source_id, text)` / `delete_embedding(db, workspace_id, *, layer, source_id)`；
  - 同步埋点：add_memory_note / delete_memory_note 后 upsert/delete；revise_setting 后按新内容 upsert（事件失败只告警的既有风格同样适用，索引失败也只告警不回滚业务）；
  - 归档笔记：不删向量（保留历史），查询时默认排除（与关键词一致）。
- tests：本地向量确定性（同文本同向量）、归一化、不同文本可区分；upsert/delete/修订同步；索引失败不阻塞业务；迁移回填；配置三来源与非法值。

### 做到什么程度

- 嵌入抽象、索引表、三类同步埋点全部落地且有单测；既有 608 测试全绿。

### 验收标准

- 单测覆盖上述全部路径；`memory reindex` 前的空索引不影响任何既有命令（fail-closed）。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 语义检索与 reindex 命令（I2）、api 后端真实验证（I2 文档说明）、其他检索层索引。

## 子阶段 I2：语义检索、reindex 与 CLI

### 做什么

- `core/retrieval.py`：
  - `semantic_search(db, workspace_id, query, top_k) -> list[SemanticHit]`：query 嵌入 → 与本作品各层向量算余弦 → 取 top_k；命中对象回读（笔记/设定），排除归档笔记与已删除 source；
  - `reindex_embeddings(db, workspace_id)`：遍历本作品笔记与设定，全量 upsert，幂等；
  - 降级：索引空、后端不可用或嵌入失败时返回空列表并 stderr 告警，调用方继续关键词检索。
- `cli/memory.py`：
  - `memory search <作品ID> <关键词> [--semantic]`：默认行为完全不变；加 `--semantic` 时合并关键词与语义命中（去重：语义命中若已被关键词层输出则不重复），语义行输出 `[笔记] ...（来源: 写手）[语义 0.87]` / `[设定] ...（来源: 作者 v2）[语义 0.91]`，按相似度降序排在关键词结果之后；
  - `memory reindex <作品ID>`：重建索引并输出条数。
- tests：无共同关键词但语义相近命中（local 后端可复现）、删除后不命中、修订设定后命中新内容、--semantic 默认关闭、降级路径（索引空/嵌入抛错）、reindex 幂等、跨作品隔离、registry 补 reindex。

### 做到什么程度

- 语义检索端到端可断言；关键词检索默认行为与既有 608 测试零回归；smoke_m3 仍 SMOKE OK。

### 验收标准

- 端到端 + 降级 + 去重 + 排序；FTS/LIKE 关键词路径不受 --semantic 影响。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3（检索耗时阈值不回归）。

### 暂不做

- 对话/意见/版本层向量索引、混合加权调参、跨作品语义检索（N10 时再议）、向量持久化格式优化。

## 子阶段 I3：文档、全量回归与收口

### 做什么

- docs/usage.md 新增「语义记忆检索（N7）」节：两档后端能力边界与配置（NOVEL_EMBEDDING_*）、--semantic 语义、[语义] 后缀与排序、reindex、降级语义、红线（不阻塞、增量一致、默认离线）；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 608+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 跨作品聚合语义视图（N10）、API 后端的部署与鉴权文档（随 N24 API 服务层再议）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
- 后续单元（N18 / N19 / N10）在 N7 收口后按 backlog 顺序另拆。

## 状态

- 立项（2026-08-19）：实施文档就绪，用户确认后拆包 I1。
- I1 完成（2026-08-19；commits 92ded53 / 85cfb01，全量 653 测试绿；嵌入抽象、索引表与增量同步 + 独立审查 P2/P3 修复，审查链归档 docs/reviews/）。I2 待拆包。
- I2 完成（2026-08-19；commits b95abd2 / b65b42c，全量 676 测试绿；语义检索、reindex 与 --semantic + 独立审查 P2/P3 修复，审查链归档 docs/reviews/）。I3 待拆包。
