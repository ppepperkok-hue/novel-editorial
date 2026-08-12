# 编辑部泛化评估与工程表 · 20260812

> 定位：把 novel-editorial 从「AI 网文流水线」升级为「多领域 AI 文学编辑部」——同一套 agent 协作框架可产出网文、正式小说、同人文与通用内容。
> 状态：评估完成，待老板确认后进入实施。

## 一、现状盘点（证据）

### 通用底座（与领域无关，可直接复用）

- 调度与状态机：`tools/workday.py`、`tools/editorial_daily.py`（手动开工、两级完工、锁、恢复）
- 协作：`tools/mailroom.py`（消息）、`tools/relations.py`（人际）、`tools/promises.py`（承诺）、`tools/write_diaries.py`（日记）、`tools/agent_states`（心情）
- 会议：`tools/agent_meeting.py` + `tools/meeting_kinds.py`（kind 声明式注册：weekly/topic/planning/critique/retro）、`tools/meeting_actions.py`、`tools/meeting_materials.py`
- 记忆与知识：`tools/agent_memories`、`tools/agent_tool_loop.py`（工具式知识调用）、`tools/knowledge_keeper.py`（知识管家）、`tools/distill_lessons.py`（经验蒸馏）
- 治理：`audit_logs`、`cost_logs`、预算熔断、`web_api`、前端面板、桌面壳

### 领域绑定（三道坎）

| 坎 | 现状 | 证据 |
| --- | --- | --- |
| 1 数据层 | novels/chapters/volumes/characters/world_events/plot_threads/quality_reports/publish_logs 等 14 张领域表与通用表混在同一 schema；`novel_id` 贯穿 42 个文件 | db.py 29 表；novel_knowledge 67 处、record_work 56、editorial_daily 56、agent_meeting 54 |
| 2 产出链路 | 写稿/润色/审稿/读者审/发布硬编码在 `editorial_daily.py`（节点名写手A/润色A/审稿A…，任务指令为网文写作）；发布直连番茄 API（fanqienovel.com，headers 写死） | editorial_daily 55-60、792-832、995-1027；publish_stock 43-47、128-174 |
| 3 Agent 职责 | prompts/agents/*.md 的「人物档案」段通用，但「日常任务」段全是番茄网文写手指令；知识包为网文技巧 | writer.md 日常任务段；prompts/knowledge/*.md |

## 二、泛化性能评分

| 维度 | 评分 | 说明 |
| --- | --- | --- |
| 协作框架（会议/消息/关系/记忆） | 4/5 | 与领域无关，kind 已声明式 |
| 调度与工作日状态机 | 4/5 | 通用，锁/恢复/两级完工 |
| 知识库与工具式调用 | 4/5 | 机制通用，schema 命名带 novel |
| 前端面板与桌面壳 | 4/5 | 页面未绑小说 |
| 数据模型抽象 | 2/5 | 无 entity 抽象，领域表混入 schema |
| 任务/产出抽象 | 2/5 | 工作流步骤硬编码，无注册表 |
| 外部适配器隔离 | 2.5/5 | 番茄直连，无 port/adapter |
| 综合 | 3/5 | 骨架通用、血肉网文 |

## 三、改造方案（三道坎）

### 坎 1 · 数据层抽象

目标：领域实体与通用协作数据分离，任何领域都有「实体 + 内容 + 元数据 + 领域知识」。

- 新增通用表：`entities`（id/kind/title/status/meta/created_at/updated_at）、`entity_content`（entity_id/seq/title/body/status）、`entity_knowledge`（entity_id/category/entity/content/version/history 迁移自 novel_knowledge）
- `novel_id` → `entity_id` 机械重命名（42 文件），保留 `novels/chapters` 兼容视图或别名列（迁移期）
- 领域专属表（characters/world_events/plot_threads 等）保留在领域包内，不进通用 schema
- 验收：现有 504 测试全绿 + 迁移兼容测试（旧库可读、新库可写）

### 坎 2 · 产出链路接口化

目标：调度器只认「工作流定义」，领域提供步骤实现。

- 新增 `tools/workflow_registry.py`：领域注册 `name / steps[] / agent_role_map / quality_rules / publisher`
- `editorial_daily.py` 拆为：通用执行器（分派→执行步骤→质量门→发布→归档）+ 网文工作流定义（写稿/润色/审稿/读者审）
- 发布适配器：`PublisherPort`（publish(entity_id, payload) / check_stock / list_books），`FanqieAdapter` 实现番茄；新增 `LocalAdapter`（导出 markdown/文件，供正式小说与同人文使用）
- 验收：网文链路行为零变化 + 新领域 dry-run 工作流跑通（本地导出）

### 坎 3 · Agent 职责模板化

目标：人格恒定，职责按领域注入。

- prompts/agents 拆为两层：`persona/*.md`（人物档案，通用）+ `domains/<领域>/roles/*.md`（职责/任务指令）
- `agent_tool_loop` 按领域加载职责段与知识包索引；知识包支持领域命名空间（writing / fanfic / general）
- 新增 `scripts/new_domain.ps1`：脚手架生成领域包（提示词模板 + 工作流定义 + 适配器骨架）
- 验收：同人/通用领域 dry-run 下 agent 能按领域指令产出；网文人格输出不变

## 四、工程表（分阶段，每阶段全绿再进下一阶段）

| 阶段 | 步骤 | 影响面 | 验证 | 估计 |
| --- | --- | --- | --- | --- |
| P0 决策 | 决策记录定稿、目标/验收/边界确认（本文件） | 无 | 老板确认 | 0.5d |
| P1 数据层 | entity 三表 + novel_id→entity_id 重命名 + 迁移兼容 | 42 文件、db.py | 504 全绿 + 迁移测试 | 1-2d |
| P2 工作流定义 | workflow_registry + editorial_daily 拆分 + 网文工作流注册 | editorial_daily、editorial_steps | 网文 dry-run 与真实链不回归 | 2-3d |
| P3 适配器 | PublisherPort + FanqieAdapter 抽取 + LocalAdapter | publish_stock、create_book、delete_book | 发布 mock 测试 + 本地导出测试 | 1-2d |
| P4 领域包 | persona/domain 拆分 + 知识包命名空间 + new_domain 脚手架 | prompts、agent_tool_loop、knowledge_keeper | 领域加载测试 | 1-2d |
| P5 新领域试点 | 「通用文章工作流」或「同人文工作流」dry-run 全链 | 新领域包 | dry-run 产出真实内容 + 全量回归 | 1-2d |
| P6 收口 | README/evolution 更新、审查一轮（含核实+回归检查）、提交 | 文档 | 全量回归 + 审查闭环 | 1d |

总计约 7-12 个工作日（按当前 CLI 并行节奏可压缩）。

## 五、风险与取舍

- 重命名风险：novel_id 机械替换可能漏改动态 SQL/前端字段 → P1 用兼容别名 + 全量测试兜底，不追求一次到位
- 工作流拆分风险：editorial_daily 是核心链路，拆坏影响日更 → P2 先抽出注册表并保持原函数签名，逐步迁移
- 发布适配器风险：番茄接口细节多 → P3 只做接口抽取，FanqieAdapter 行为逐字节不变，不重构实现
- 范围控制：P4 之前不做「新领域真正上线」，只做 dry-run 验证；真实多领域运营是 P5 之后的事
- 可回退：每阶段独立提交，P1-P5 均可单独回退；旧库不迁移也能继续跑（兼容层）

## 六、一句话结论

编辑部底座已经通用（会议/记忆/关系/调度/面板），网文只是第一个领域包；把三道坎走完，系统就从「网文流水线」变成「可插拔的多领域编辑部」。
