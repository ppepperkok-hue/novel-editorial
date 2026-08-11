# 人格化大工程（R0–R4）审查报告 · 2026-08-11

## 范围

本次审查覆盖人格化大工程全部实施内容：R0 四刀（分派生效/认领兑现/表达出口/议题闭环）、R1 行为选择权（任务响应/消息回路/认领执行）、R2 社会性（关系权重/心情注入/关系事件）、R3 自主与成长（agency 白名单/观点演化/反思趋势）、R4 编辑部生活（工作日状态机/会议泛化/仪式感）。

测试基线：后端 437 + 前端 16 全绿；每次提交前全量回归。

## P0（必须立即修复）

无。

## P1（高风险，已修复）

| 问题 | 证据 | 修复 |
| --- | --- | --- |
| `workday.resume` 与 `workday.close` 无原子锁保护，与并发 `open` 可能交叉写 | `tools/workday.py`（resume/close 直接执行无 acquire_lock） | resume/close 均加 preflight 锁 + finally 释放；新增锁占用测试 |
| `workday.open` 允许在上一工作日 `awaiting_close` 时重复开工，产生两个并存工作日 | open 无活跃工作日检查 | open 前检查 `source='workday' AND status='running'`，未收工则拒绝并提示；新增拒绝测试 |

## P2（低风险，接受或跟踪）

| 问题 | 影响 | 处置 |
| --- | --- | --- |
| `free` 模式晨会调用 eic 无显式重试 | 单次网络抖动时降级为确定性计划 | 可接受：降级不阻塞，后续可加 agent_tool_loop 重试 |
| 收工/开工/里程碑公告按 11 位 agent 各发一条 | 消息流 11 条/事件 | 语义正确（消息总线按人投递），前端已按收件箱分组 |
| `_meeting_directives` 只取最近一次会议 | 多会议并存时旧共识被覆盖 | 符合「最近共识」语义，如需多会议合并再单独开项 |
| 里程碑公告按 `detail LIKE` 去重 | 大表扫描慢 | 数据量小（审计行级），暂不索引 |

## P3（文档与体验）

- README/evolution.md 数字与代码同步（本次一并更新）。
- 会议产出卡片在档案页以 chip 展示（蓝图/行动项/写作指令），完整 JSON 可展开；前端详细产出卡片后续可增强。

## 影响评估表

| 阶段 | 改动面 | 影响的既有功能 | 回归证据 |
| --- | --- | --- | --- |
| R0 | config / editorial_daily / steps / record_work / dashboard / meeting_session / 前端章节阅读器 | 日更链、质量落库、会议收尾 | 437+16 全绿 |
| R1 | config / editorial_daily / mailroom / agent_context / activity | 分派、消息、任务板、认领 | 437+16 全绿 |
| R2 | config / editorial_daily / agent_context / architect_weekly | 分派输入、打回措辞、注入快照 | 437+16 全绿 |
| R3 | config / agency 新模块 / write_diaries / agent_context / architect_weekly / 前端 Agent 管理 | 周记、注入、面板 | 437+16 全绿 |
| R4-1 | db / editorial_daily / workday 新模块 / control / web_api / reminders 新模块 / 前端首页 | 调度入口、状态卡、执行记录 | 437+16 全绿 |
| R4-2 | meeting_kinds / meeting_materials / meeting_actions 新模块 / agent_meeting / meeting_session / 前端会议中心 | 会议引擎、材料、议程 | 437+16 全绿 |
| R4-3 | workday（开工/里程碑公告） | 工作日收尾 | 437+16 全绿 |

## 结论

本次改造无 P0 遗留；P1 两项已在审查中修复并补测试。核心风险点（行为选择权、工作日并发、会议路由）均有开关、锁与幂等保护，可回退。后续迭代建议：R1-2 消息「重做」当前落为行动项回路，如需管线内即时重写需单独设计防循环；free 会议与多会议共识合并列为候选增强。
