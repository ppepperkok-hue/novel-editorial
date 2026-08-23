# M5 实施真元文档（自由意志 · N29 编辑部自然讨论）

## 总览

- **大阶段**：自由意志第三阶段（立项清单 docs/project-plan/12-n29-checklist.md，设计结论 docs/project-plan/09-free-will-design.md 收口补充）。
- **当前只拆 N29**；三阶段路线在本单元收口后完整。
- **N29 一句话**：伙伴耐心池见底时，编辑部自己把讨论开起来——点好人、通气、总结、落盘；作者旁听、随时拍板，创作链依旧由作者把守。
- **现状**：N28 已收口（耐心池三状态 + 见底可见 + 冲突中和，1392 测试）；N4 讨论形态已收口（open_discussion / contribute_to_discussion / summarize_discussion / conclude_discussion）。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；触发、召集、冷却、未解决重新攒逐条可断言；全部旧行为不破坏。

## 红线（继承 09 / 12，本阶段强制）

1. **讨论是协作链**：自然召集只产生对话与留痕，不写正文、不改稿、不自动拍板；作者拍板即收敛。
2. **事件驱动、无定时器**：触发只挂在三状态累积点（decision reject / talk override / summarize 分歧）之后，不设后台扫描。
3. **防风暴**：同议题触发后清零进冷却，冷却内不重复召集；未解决且冷却过才重新攒。
4. **可解释、可复现**：每次召集有 source 可溯；无随机不可复现路径。

## 地基影响评估（先评估再动工）

- **behavior_timeline 扩展**：BEHAVIOR_KINDS 增加 `cooldown`（议题冷却标记）；加性扩展，无表结构迁移。
- **触发与召集新模块** `core/natural_discussion.py`：触发判定（耐心池见底 + 议题冷却检查）与自然召集（复用 N4 discussion 接口）；依赖方向 core → core 合法。
- **冷却记录**：触发后落 kind=cooldown（source=discussion:summoned、target=议题、after_value=池值摘要）；议题是否冷却 = 同 (agent, target) 最近一条 cooldown 距今是否超冷却期（常量定义，注释依据）。
- 事件契约、错误码、依赖方向不变；若发现必须改既有表 / 契约，先停下回报。

## 子阶段 S1：触发判定（N29-A）

### 做什么

- BEHAVIOR_KINDS 加 `cooldown`（record 白名单同步）。
- `core/natural_discussion.py`（新建）：`summon_candidates(db, workspace_id, now=None)`——耐心池见底（pool==0）且该伙伴近期未因同议题触发（无 cooldown 或已超冷却期）的伙伴列表；`within_cooldown(...)` 判定；开关复用 proactive_enabled（关掉全静默，不自然召集）。
- 触发点：三状态累积路径（decision reject、talk override、summarize 分歧）之后调用检查（走 safe 降级，失败不反噬业务）。

### 做到什么程度

- 池底候选、议题冷却判定可断言；开关关不触发；无定时器；既有全部测试不破坏。

### 验收标准

- 单测：候选集合、冷却期内跳过、冷却过期重新候选、开关、边界（池不为 0 不触发）。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 实际召集（S2）；清零与冷却写回（S3）；可见性与文档（S4）。

## 子阶段 S2：自然召集（N29-B）

### 做什么

- `summon_natural_discussion(db, workspace_id, agent, now=None)`：以候选伙伴为分歧一方，点将另一方（按议题取 override/conflict 记录中的对方；找不到则默认写手 / 审稿配对）+ 主编为总结人；走 open_discussion → 双方 contribute → summarize_discussion，全程确定性模板；落 agent.message 事件（payload 带 initiator=agent、kind=natural_discussion、trigger=patience_exhausted）。

### 做到什么程度

- 端到端：池底 → 自然召集 → 讨论记录齐全（点将 / 通气 / 总结 / 落盘）；不写正文；作者可后续 conclude 拍板。

### 验收标准

- 端到端用例：讨论 message/event 齐全、payload 可解释、正文无变化；失败降级用例。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 冷却写回（S3）、可见性命令（S4）。

## 子阶段 S3：清零与冷却（N29-C）

### 做什么

- 召集成功后：落 kind=cooldown 记录（source=discussion:summoned）；对候选伙伴的相关 conflict 追加中和记录（复用 N28 RESOLVED_SOURCE 或等价），使池清零。
- 未解决重新攒：若讨论 conclude 未解决（或未拍板），冷却期过后新的分歧继续累积，重新触发；作者拍板即收敛（复用 N28 conclude 中和）。

### 做到什么程度

- 同议题冷却内不重复召集；未解决且冷却过重新攒满再触发；拍板收敛；防风暴可断言。

### 验收标准

- 集成用例：触发→冷却→冷却内不重复→冷却后未解决重新攒→拍板收敛。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 面板可视化（后置）。

## 子阶段 S4：可见性、文档与收口（N29-D）

### 做什么

- 事件流 / talk list 可见自然召集（payload 标记）；docs/usage.md 补「编辑部自然讨论（N29）」节：触发条件、冷却、作者拍板、红线；示例 mock 实跑。
- 全量回归 + smoke_m3 + stress_m3 + 独立审查归档。

### 做到什么程度

- 每次召集可解释；文档与行为一致、示例实跑；全量绿，审查链收敛 Ready。

### 验收标准

- 文档实跑；审查归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 面板可视化（后置面板阶段）；三阶段之后的自由意志新能力（待用户另立项）。

## 任务包规划（09a 文件不相交）

- 包 M5-N29-S1：behavior.py + core/natural_discussion.py（新）+ 触发点接线（decision/talk/discussion）+ 相关测试。
- 包 M5-N29-S2：core/natural_discussion.py 召集实现 + 相关测试。
- 包 M5-N29-S3：core/natural_discussion.py 冷却写回 + core/patience.py 池清零联动 + 相关测试。
- 包 M5-N29-S4：docs/usage.md + 全量回归 + 审查归档。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报四段，经总监确认后再进下一子阶段。

## 状态

- S1 完成（2026-08-24）：cooldown 行为 kind + core/natural_discussion.py 触发判定（池底候选 / 议题冷却 / 开关）+ 三累积点接线，commits 7ae1f3e / c182f29；全量 1416 测试绿；独立审查 2 条意见已修复复核收敛，归档 docs/reviews/20260824-M5N29S1-initial.md。
- 待办：S2 自然召集（点将分歧双方 + 主编，走 N4 discussion 形态）。
