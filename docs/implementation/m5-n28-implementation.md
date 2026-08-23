# M5 实施真元文档（自由意志 · N28 反馈闭环与沉默）

## 总览

- **大阶段**：自由意志第二阶段（立项清单 docs/project-plan/11-n28-checklist.md，设计结论 docs/project-plan/09-free-will-design.md）。
- **当前只拆 N28**；N29 编辑部自然讨论只保留方向（状态攒满自动发起是 N29 的活）。
- **N28 一句话**：让伙伴的行为有后果——被拒会低落、被采纳会起劲、想说没说留得下账、憋久了攒得出火气；作者用说话而不是拧数值影响他们。
- **现状**：N27 已收口（动机表 / 选择器 / 个性参数 / 旋钮，1307 测试）；behavior_timeline 有 impression/relationship/viewpoint 三类；N2 作者推翻已有 source=override:<rule>；discussion 分歧只有消息标记、未沉淀。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；反馈闭环、沉默留痕、耐心池、LLM 提炼开关逐条可断言；全部旧行为不破坏。

## 红线（继承 09 / 11，本阶段强制）

1. **反馈不反噬业务**：回写动机 / 漂移 / 沉默失败只告警、不回滚业务结果（沿用 N3 降级模式）。
2. **沉默可选、不惩罚**：沉默是自然行为，连续沉默只降倾向、有下限，不设关卡。
3. **不失控**：数值漂移有上下限；耐心池见底只记账与可见，不自动行动（N29）。
4. **可解释、可复现**：每条反馈 / 沉默 / 耐心变化有 source 可溯；无随机不可复现的路径。

## 地基影响评估（先评估再动工）

- **behavior_timeline 扩展**：BEHAVIOR_KINDS 增加 `silence`（沉默）与 `conflict`（分歧未决）；加性扩展，不迁移表结构。
- **Agent 加四列** `drift_proactivity` / `drift_stubbornness` / `drift_talkativeness` / `drift_patience`（int，默认 0，范围 -10..10，Alembic 加性迁移）；有效参数 = clamp(档案基线 + drift, 0, 10)；drift 按懒惰时间向 0 回弹（每次触碰结算）。
- **耐心池无新表**：从 behavior_timeline 现算——被拒（decision:reject / delegation:refused 的 relationship 行）、被压下（source 以 override: 开头的 viewpoint 行）、分歧未决（kind=conflict 的行）；池值 = clamp(patience 有效值 - 消耗，0, 10)。
- **LLM 提炼**：derive_motives 增加可选 client 参数；开关关时走确定性模板（零 token），开时用 client 生成动机 content（mock 下可断言）。
- 事件契约、错误码、依赖方向不变；若发现必须改既有表 / 契约，先停下回报。

## 子阶段 S1：行为类型扩展与个性漂移地基（N28 前置）

### 做什么

- BEHAVIOR_KINDS 加 `silence` / `conflict`（record_behavior_entry 白名单同步，时间线查询兼容）。
- Agent 四列 drift_* + Alembic 加性迁移（默认 0，旧行回填）。
- `core/evolution.py`（新建）：`effective_param(agent, field)`（基线 + drift 钳制）、`apply_param_drift(db, workspace_id, agent_id, field, delta)`（drift 钳制 -10..10、写 behavior_timeline 留痕 source=drift:<event>）、`rebase_param_drift(db, workspace_id, agent_id, now=None)`（懒惰回弹：按整天数向 0 折返，幂等）。
- 选择器组装处（proactive._load_choice_inputs）改用有效参数。

### 做到什么程度

- 有效值 / 钳制 / 回弹 / 留痕可断言；旧库迁移幂等；既有全部测试不破坏。

### 验收标准

- 单测：drift 越界钳制、有效值 clamp、回弹幂等与单调、留痕 source、迁移回放。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 真实路径写入漂移（S2）；沉默落库（S3）；耐心池（S4）；LLM 提炼（S5）。

## 子阶段 S2：反馈闭环（N28-A / N28-B）

### 做什么

- 行为结果回写动机：decide(action=reject) 后写手 pending_issue 动机 strengthen、accept 后 clear/降相关动机；delegation refused/accepted 回写委托方动机；talk 点名表扬/批评（识别语气的确定性规则）strengthen 对应动机。全部走 `_safe` 降级。
- 作者「放下」指令：`motives drop <作品ID> <动机ID>`（等价 clear_motive，来源留痕 author_feedback）；talk 中作者说「那个先放下吧」等确定短语触发对应 pending_issue 清空。
- 个性漂移写入：被拒 +stubbornness drift（坚持度上升）、被采纳 +proactivity（起劲）、连续被压下 +patience 消耗方向（S4 结算，本步只写 stubbornness/proactivity 两例，注释依据）。

### 做到什么程度

- 端到端：真实 decide / delegation / talk 路径 → 动机强度变化 + drift 留痕可断言；回写失败业务仍成功。

### 验收标准

- 每类路径至少一个端到端用例 + 失败降级用例；作者放下/言语反馈有来源留痕。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 沉默（S3）、耐心池（S4）、参数回弹在真实路径的长期观测。

## 子阶段 S3：沉默留痕（N28-D）

### 做什么

- 选择器评估后：候选相关、最高权重低于显著线、且该伙伴对同议题的倾向较上次记录有变化时，落 `silence` 时间线记录（source=trigger，summary=评估倾向摘要）；连续沉默倾向不动不重复记；不相关不回不记。
- `behavior show` 扩展或 `silence list` 命令（动词-宾语）查看沉默记录。

### 做到什么程度

- 相关且变化的沉默可断言；同议题连续沉默去重；时间线计数不刷屏（上限测试）。

### 验收标准

- 集成用例：评估→沉默落库 / 无关不落 / 连续沉默不重复 / CLI 可见。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 沉默反哺倾向的完整闭环（回弹留 N28-C 既有机制）；面板可视化。

## 子阶段 S4：耐心池（N28-E）

### 做什么

- `core/patience.py`（新建）：三状态计数（被拒 / 被压下 override / 分歧未决 conflict）、事件驱动「无视」判定（下次触碰同议题时回看上次意见悬置时长）、`patience show <作品ID>` CLI（池值 + 三状态明细，作者可见）。
- 分歧未决沉淀接线：discussion 分歧未解决时落 kind=conflict 记录。

### 做到什么程度

- 三状态计数正确、池值可见、见底仅展示（不行动）；无视判定事件驱动、不设倒计时。

### 验收标准

- 集成用例：拒绝/压下/分歧各计各账；池值计算与 CLI 输出可断言。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 攒满自动召集讨论（N29）、冷却防风暴（N29 一起做）。

## 子阶段 S5：LLM 提炼、文档与收口（N28-F / N28-G）

### 做什么

- derive_motives 接 LLM 提炼：motive_llm_enabled 关 → 确定性模板（现状）；开 → client 生成动机 content（mock 可断言），失败降级回模板并告警。
- docs/usage.md 补「反馈与沉默」节；.env.example / config.example.toml 同步（无新键则不变）；全量回归 + smoke_m3 + stress_m3 + 独立审查归档。

### 做到什么程度

- 开关对照可断言、关时零 token；文档与行为一致、示例实跑；全量绿，审查链收敛 Ready。

### 验收标准

- 开关对照 + 失败降级用例；文档实跑；审查归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板可视化（后置）；N29（本单元收口后另立项）。

## 任务包规划（09a 文件不相交）

- 包 M5-N28-S1：behavior.py + models.py + 迁移 + core/evolution.py（新）+ proactive.py 有效参数接入 + 相关测试。
- 包 M5-N28-S2：core/decision.py + core/delegation.py + core/chat.py + cli/motives.py + 相关测试。
- 包 M5-N28-S3：core/choice.py 评估调用侧 + core/behavior.py + cli 可见命令 + 相关测试。
- 包 M5-N28-S4：core/patience.py（新）+ core/discussion.py + cli/patience.py（新）+ 相关测试。
- 包 M5-N28-S5：core/motives.py + docs + 全量回归 + 审查归档。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报四段，经总监确认后再进下一子阶段。

## 状态

- S1 完成（2026-08-23）：silence / conflict 行为 kind + drift 四列迁移 + core/evolution.py（有效参数 / 漂移写入 / 懒惰回弹），commits 8686113 / 3fdcb8a；全量 1331 测试绿；独立审查 P1+P3 已修复复核收敛，归档 docs/reviews/20260823-M5N28S1-initial.md。
- S2 完成（2026-08-23）：decide / delegation / talk 反馈闭环（动机回写 + 作者放下 / 言语反馈 + 漂移写入），commits 85a05b6 / 5d15e0b；全量 1353 测试绿；独立审查 2 条 P3 已修复复核收敛，归档 docs/reviews/20260823-M5N28S2-initial.md。
- S3 完成（2026-08-23）：沉默留痕（相关 + 显著线 + 倾向变化三门槛、连续沉默去重、safe 降级），commit e3350dc；全量 1363 测试绿；独立审查零意见，归档 docs/reviews/20260823-M5N28S3.md。
- S4 完成（2026-08-23）：耐心池三状态记账 + 悬置天数懒惰结算 + patience show CLI + 分歧未决沉淀与拍板中和，commits e9483b0 / ab90d78；全量 1383 测试绿；独立审查 2 条 P2 已修复复核收敛，归档 docs/reviews/20260823-M5N28S4-initial.md。
- 待办：S5 LLM 提炼实装、文档与收口（usage「反馈与沉默」节 + 全量回归 + smoke_m3 + stress_m3 + 独立审查归档）。
