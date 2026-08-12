# 编辑部泛化 · Phase 0 决策记录（v3）

> 日期：2026-08-12
> 状态：v3 已执行归档与清理，领域包设计待讨论
> 前置评估：`docs/planning/20260812-generalization-assessment.md`

## 0. 版本变更

### v2（老板指示 20260812）

- 前端（面板领域切换等 UI）**延后**：本次只做壳与接口，前端后续单独排。
- 现有网文实现**不再作为改造兼容约束**：不要求「网文零回归 / FanqieAdapter 行为不变 / novel_id 兼容层」；网文相关代码与测试**归档为参考实现**，以后需要时按领域包重新做 agent 适配。
- 领域包（网文/正式小说/同人文等）**延后**：本次先做「壳的泛化机制」，领域包的具体实现 P5 之后按需做。

### v3（归档与清理已执行 20260812）

- **网文领域资产已归档**：`prompts/knowledge/` 6 个网文知识包移入 `tools/archive/novel-writing/knowledge/`；`ai_taste_check.py`、`editorial_steps.py` 及 4 份网文人设提示词（writer/editor/reviewer/planner）存参考副本于 `tools/archive/novel-writing/`；原文件保留（P2/P4 拆分时再删引用，避免现在破坏壳）。
- **自动发书保留**：publish_stock/create_book/delete_book/get_meta/record_work/check_stock/collect_reader_stats/current_book 全部保留原位，作为壳的发布能力与参考。
- **旧网文库已删除**：根 demo.db、backups/ 12 份备份、构建种子库、exports/archive 清理前备份、n8n_tmp 测试残留全部清除；网文旧数据不再存在。
- **回退点已固化**：git tag `pre-generalization` 打在归档前 commit，完整网文实现可随时回退。
- **领域包设计待讨论**：具体领域包怎么做、适配什么形态，先讨论清楚再进 P1。

## 1. 目标与验收标准

**目标**：把 novel-editorial 重构为「多领域 AI 编辑部壳」——同一套 agent 协作壳（调度/会议/消息/记忆/关系/知识库/审计）不绑定任何领域；新领域通过脚手架生成领域包（实体模型 + 工作流定义 + 适配器 + 知识库 + 职责提示词）接入，核心壳零改动。网文实现归档为参考，不作为兼容约束。

**验收标准**：
1. 壳无领域痕迹：`rg -n "novel_id|章节|番茄|写手" novel_editorial tools --glob "*.py"` 仅命中领域包/归档目录。
2. 领域包可插拔：`new_domain` 脚手架生成骨架后能注册进 workflow_registry 并 dry-run 跑通，核心壳零改动。
3. 数据隔离：每领域独立数据库（entities/entity_content/entity_knowledge 通用表），互不污染。
4. 参考领域落地：P5 交付「通用文章」领域包，dry-run 产出真实内容，证明「配模板即可接领域」。
5. 核心测试全绿：壳相关测试（会议/消息/记忆/调度/知识/审计）重构后全绿；网文专属测试归档不参与门槛。

## 2. 领域包契约（一个领域 = 五件套）

| 组件 | 内容 | 现有对应 |
| --- | --- | --- |
| 实体模型 | 实体/内容/元数据/领域知识表结构 | 新 entity 三表（P1），网文 novels/chapters 归档参考 |
| 工作流定义 | 步骤序列、agent 角色映射、质量规则 | 新 workflow_registry（P2），editorial_daily 网文链归档参考 |
| 适配器 | 发布/采集/外部集成 | 新 PublisherPort（P3），FanqieAdapter 归档可选 |
| 知识库 | 领域技巧/设定/规则包 | prompts/knowledge 命名空间化（P4） |
| 职责提示词 | 人格复用 + 领域职责注入 | prompts 拆分 persona/domains（P4） |

## 3. 用户边界（哪些自动化、哪些人工）

- 自动化：壳的全部能力（调度/会议/记忆/知识/审计）；领域包注册与 dry-run 验证。
- 人工：新领域接入时的领域定义由老板确认；真实发布前人工审；领域包验收老板拍板。
- 本次不做：前端 UI（面板切换等延后）；「无代码配领域」的 GUI 设计器（脚手架生成代码骨架即可）；网文领域包重新实现（归档后按需再做）；恢复已删除的网文旧数据（不可恢复，回退点是代码不是数据）。

## 4. 预算与规模

- 周期：P1-P6 约 7-10 个工作日（CLI 并行节奏）。
- API 成本：不新增调用类型，成本结构不变；领域 dry-run 走现有 mock 或 flash。
- 存储：每领域独立 sqlite；网文旧库保留不动；新领域库由脚手架初始化。

## 5. 技术栈

- 不变：Python 调度器 + sqlite + DeepSeek（deepseek-v4-flash/pro）+ web_api + React 面板 + Electron 壳。
- 新增：`workflow_registry.py`、`publisher.py` 端口层、`new_domain.ps1` 脚手架、`prompts/persona/` 与 `prompts/domains/` 目录。
- 归档：网文知识包、质检与写作步骤参考、网文人设提示词副本 → `tools/archive/novel-writing/`（gitignore 内）；editorial_daily 网文链与发布链保留（P2 拆分）。

## 6. 外部依赖

- 番茄发布：保留现状（自动发书能力不丢）；以后做网文领域包时再按 PublisherPort 重新适配。
- 本地导出：LocalAdapter（markdown 落盘），无外部依赖，作为参考领域默认适配器。
- 参考领域「通用文章」：无平台依赖，纯本地产出。

## 7. 工程表（每步验收标准）

| 阶段 | 步骤 | 验收标准（可执行） | 估计 |
| --- | --- | --- | --- |
| P0 决策 | 本文件 v2 定稿 + 老板确认 | 确认签字（对话确认即可） | 0.5d |
| P1 数据层 | entity 三表；壳与领域解耦（网文表归档）；web_api/库切换；测试按壳/领域重组 | 壳测试全绿；`rg -n "novel_id" novel_editorial tools` 仅命中 archive 与新领域包；旧网文库可读（归档脚本） | 1-2d |
| P2 工作流注册表 | workflow_registry.py；通用执行器（步骤序列 + agent 角色 + 质量规则来自领域定义）；editorial_daily 网文链归档 | 注册表可注册/列出领域；通用执行器 dry-run 空领域包跑通；archive 内网文链可被参考 | 2-3d |
| P3 适配器层 | PublisherPort（publish/check_stock/list）；LocalAdapter（markdown 落盘）；FanqieAdapter 归档 | LocalAdapter dry-run 导出合法文件；端口可插拔（换 adapter 不换调用方）；端口层测试全绿 | 1-2d |
| P4 领域包拆分 | prompts 拆 persona/domains；知识库命名空间；new_domain.ps1 脚手架 | 领域加载测试（按领域注入职责段与知识索引）；脚手架生成最小领域包可注册并 dry-run；网文提示词归档 | 1-2d |
| P5 参考领域 | 「通用文章」领域包完整实现（实体/工作流/本地导出/知识包/提示词） | dry-run 产出真实文章并落盘；壳零改动；核心测试全绿（前端不做，领域切换接口已留） | 1-2d |
| P6 收口 | README/evolution 更新；审查一轮（核实→族级治理→回归检查→归档） | 审查闭环无 P1；README 文档化领域包接入步骤；提交 | 1d |

## 8. 风险与取舍

- 大重构风险：去掉网文兼容约束后改动面大 → 每阶段独立提交可回退；网文代码先进 archive 再删引用，不一次性删除。
- 测试重组风险：网文专属测试归档后壳测试减少，覆盖面依赖新测试 → P1 同步补壳测试（会议/消息/记忆/调度/知识/审计），P5 用参考领域验证端到端。
- 数据安全：网文旧库只读归档，不迁移不删除；新架构从空库开始。
- 范围控制：前端延后；领域包（含网文重做）P5 之后按需做；本次只交付壳 + 参考领域。
- 可回退：P1-P6 每阶段独立提交；archive 保留全部网文实现，任何一步可回退到网文链路。

## 9. 一句话结论

编辑部壳已是通用资产；本次按「壳 + 领域包」重构，网文实现归档为参考、不再当兼容包袱——目标形态是可插拔的多领域编辑部平台，接新领域从改代码变成配模板。
