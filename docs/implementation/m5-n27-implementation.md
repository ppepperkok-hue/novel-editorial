# M5 实施真元文档（自由意志 · N27 动机与行为选择器）

## 总览

- **大阶段**：自由意志深化（设计结论见 docs/project-plan/09-free-will-design.md，立项清单见 docs/project-plan/10-free-will-checklist.md）。
- **当前只拆 N27**（动机与行为选择器）；N28 反馈闭环与沉默、N29 编辑部自然讨论只保留方向，不预拆细节（05a 纪律）。
- **N27 一句话**：给伙伴装上「心里惦记的事」和「按倾向做选择」的能力——动机显式落库、可查可演化，行为由三层管线（粗筛 → 权重 → 加权随机）选出候选，同一件事不再只有一个答案；个性参数与自由旋钮决定编辑部有多野。
- **现状**：
  - proactive.py：情境 + 条件函数 + 固定文案 + 频次上限，确定性触发（N1）；
  - behavior_timeline 已承载印象 / 关系 / 观点与 refusal/override 来源（N3），可作历史反馈计数底座；
  - Agent 档案无个性参数字段；N17 记忆衰减（strength / last_accessed_at / decay）可复用；
  - Settings 已有 proactive_enabled / proactive_max_per_agent。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；验收五条（变体 / 演化 / 开关 / 不失控 / 可解释）逐条可断言；N1 既有行为与全部旧测试不破坏。

## 红线（继承 09 / 06，本阶段强制）

1. **动机 ≠ 待办**：无时限、无催办、可搁置可淡忘，只影响行为倾向；不得滑向任务队列 / 认领 / 超时语义。
2. **不工单化、不设强制关卡**：主动仍是可选的自然协作形态；作者永远可介入、可拍板。
3. **可解释、可复现**：每条自主行为可追溯到动机与情境；加权随机固定 seed 复现、换 seed 才有变体。
4. **创作链守门**：N27 只改「说不说、说什么」，不碰正文的写 / 改 / 拍板（守门粒度见 09）。
5. **兼容 N1–N3/N16/N17**：既有固定文案的五个注册行为先原样迁移为「单候选、权重恒最高」的模板，行为不变；事件契约、错误码、依赖方向不变。

## 地基影响评估（先评估再动工）

- **新表 `agent_motives`**（Alembic 加性迁移，不重写旧数据）：id / workspace_id / agent_id / kind（枚举：foreshadow | conflict | goal | impression | pending_issue）/ content / strength（int，默认 100）/ source / created_at / last_touched_at。动机是作品内数据，按 workspace 隔离。
- **Agent 表加四列**（个性参数，0–10 整数，带默认值）：proactivity / stubbornness / talkativeness / patience；走同一迁移，加性变更。
- **Settings 新增**：`freedom_dial: float = 0.0`（0–1）、`freedom_seed: int = 42`、`motive_llm_enabled: bool = False`；支持 NOVEL_FREEDOM_DIAL / NOVEL_FREEDOM_SEED / NOVEL_MOTIVE_LLM_ENABLED 与 config.toml `[defaults]` 覆盖；非法值报 CONFIG_ERROR。
- **事件契约、错误码、依赖方向（cli → core → store）不变**；N28 的 LLM 提炼只留开关与空钩子，不实现。
- 若实现中发现必须改既有表结构 / 事件契约 / 错误码，先停下回报，不硬做。

## 子阶段 S1：动机表、动机服务与 CLI（N27-A / N27-B）

### 做什么

- `store/models.py` 新增 `AgentMotive`；Alembic 迁移新增 `agent_motives` 表（幂等，新旧作品库均可升级）。
- `core/motives.py`（新建）：
  - `derive_motives(db, workspace_id, event_kind, context)`：确定性规则映射事件 → 动机（如 draft_generated → 写手 goal「新章已交」、refusal → 被拒方 pending_issue、review_conflict → 审稿 foreshadow 等；模板确定性、mock 下可断言）；
  - `strengthen_motive` / `decay_motives`（复用 N17 整天数衰减口径）/ `clear_motive`（了结：伏笔回收、分歧解决、作者「放下」）；
  - `list_motives(db, workspace_id, agent_id=None)`：按 strength 降序、created_at 升序。
- `cli/motives.py`（新建）：`motives list <作品ID> [--agent <别名>]`，输出伙伴 / 类型 / 内容 / 强度 / 来源 / 最后触碰时间。

### 做到什么程度

- 端到端「事件 → 产生动机 → 增强 → 衰减 → 清空」可断言；动机可查；动机 ≠ 待办有专项测试（无时限字段、无可认领语义）。
- 既有全部测试不破坏。

### 验收标准

- 单测：迁移幂等；derive 各规则映射；strength 边界（0–100）；衰减同 N17 口径；clear 语义；list 排序与过滤。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 动机强度的人工干预 CLI（后置）；LLM 提炼（N28）；动机进选择器（S3）；衰减调度器（沿用懒惰时间）。

## 子阶段 S2：个性参数四字段（N27-C）

### 做什么

- `store/models.py` 的 Agent 加 proactivity / stubbornness / talkativeness / patience 四列（0–10，默认值按角色给：主编 patience 高、审稿 talkativeness 低、写手 proactivity 中、责编 stubbornness 中；具体默认值在任务包内定，必须有依据）。
- 配置不覆盖档案值（档案是作品内数据）；`agents show` 输出四参数（最小呈现，格式不破坏旧输出断言）。

### 做到什么程度

- 字段可查可改（既有 agents 编辑命令或新增最小编辑命令）；非法值（越界 / 非整数）报用法错误；默认值合理且有注释依据。

### 验收标准

- 单测：四字段读写、越界报错、默认值断言、agents show 输出。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 参数进选择器（S3）；参数漂移 / 演化（N28）；面板可视化（后置）。

## 子阶段 S3：行为选择器（N27-D）

### 做什么

- `core/choice.py`（新建，三层管线）：
  - `coarse_filter(trigger, candidates, agents)`：确定性粗筛——角色职责、议题关键词、动机命中；不相关伙伴零成本跳过；
  - `compute_weights(candidates, motives, params, feedback)`：倾向 = 情境相关度 × 动机强度 × 个性参数 × 历史反馈（历史反馈用 behavior_timeline 的 refusal/override 计数折算）；归一化；
  - `pick_candidate(weighted, dial, seed)`：加权随机；dial=0 永远取最高权重（确定性）；dial>0 可能取低权重候选；seed 固定则复现、换 seed 有变体。
- 候选模板：沿用 N1 五个注册行为的文案作为模板库，模板可带占位符（沿用现有 Template 渲染）。

### 做到什么程度

- 同 seed 完全复现、换 seed 出现变体（测试断言）；dial=0 确定性；被拒计数上升时同类倾向下降（演化断言，N27 范围）；沉默评估入口：权重低于阈线即「不开口」（只计算倾向，不落库，落库留 N28）。

### 验收标准

- 单测：粗筛命中 / 跳过；权重四样组合与归一化；seed 复现与变体；dial 极值；被拒计数对倾向的单调影响；低权重不开口（返回空候选）。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- LLM 候选（N28）；沉默落库（N28）；状态阈值触发（N28/N29）；语气变体的 LLM 生成。

## 子阶段 S4：触发点接入与旋钮开关（N27-E / N27-F）

### 做什么

- proactive.py 的评估路径改为：事件 → coarse_filter → compute_weights → pick_candidate → 记录消息（频次上限与 proactive_enabled 仍生效）；N1 五个注册行为迁移为模板（单候选、权重恒最高），旧 payload / 文案 / 事件不变。
- `freedom_dial` 接入（作品级读 Settings；伙伴级覆盖留 N28）；`freedom_seed` 固定随机源；`motive_llm_enabled` 开关占位——开启时仅告警「LLM 提炼未实现（N28）」，不静默吞掉。
- 触发点覆盖既有 business events：talk / draft generate / draft revise / review add / decision / style set / plot plant。

### 做到什么程度

- 旧行为全兼容（N1 场景输出不变）；dial=0 下全链路确定；proactive_enabled 关闭全静默；motive_llm_enabled 开启有显式告警且行为不变。

### 验收标准

- 端到端：既有五个 N1 场景输出与旧一致；新动机命中后同一事件出现候选；dial 与开关各极值可断言；错误路径（设置非法）报 CONFIG_ERROR。

### 验证方式

pytest（新增 + 回归）+ smoke_m3 + stress_m3。

### 暂不做

- LLM 候选内容（N28）；伙伴级 dial 覆盖（N28）；面板可视化（后置）。

## 子阶段 S5：可见性、文档与收口（N27-G）

### 做什么

- `motives list` 输出完善（含强度与来源，可解释红线）；docs/usage.md 补「自由意志 · 动机与选择」节：动机语义、个性参数、自由旋钮、开关、可解释与可复现说明；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/；验收五条逐条写成可执行测试或文档断言。

### 做到什么程度

- 作者通过 CLI 看到伙伴动机、行为来源；文档与行为一致、示例可复现；全量测试、smoke_m3、stress_m3、宪法全绿，审查链收敛 Ready。

### 验收标准

- 验收五条（变体 / 演化 / 开关 / 不失控 / 可解释）各有断言；文档示例实跑；审查归档。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板可视化（后置）；N28 / N29（本单元收口后另立项拆包）。

## 任务包规划（09a 文件不相交）

- 包 M5-N27-S1S2：数据地基（models + 迁移 + 配置 + core/motives.py + cli/motives.py + 相关测试）。
- 包 M5-N27-S3：core/choice.py + 相关测试（不碰包 1 文件）。
- 包 M5-N27-S4：proactive.py 接入 + 触发点 + 旋钮开关 + 相关测试。
- 包 M5-N27-S5：文档、全量回归、验收五条断言、审查归档（S5 收口由总监复核，代码部分随 S4 一起审查）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报四段，经总监确认后再进下一子阶段。
- N28 / N29 在 N27 收口后按 backlog 另立项拆包。

## 状态

- 立项（2026-08-23）：设计讨论与 Phase 0 立项清单已确认；本实施文档拆分 S1–S5；待拆包派工。
