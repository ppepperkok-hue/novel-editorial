# 自由度补完 R5 审查报告 · 2026-08-12

## 范围

R5-1 即时重写（消息驱动的管线内重写回环）与 R5-2 记忆可控性（角色过滤注入 + memory_used 使用痕迹）。承接 `docs/planning/自由度补完评估与工程表.md`。

测试基线：后端 448 + 前端 16 全绿；相关单测 72 全绿。

## P0（必须立即修复）

无。

## P1（高风险，已处理）

| 问题 | 证据 | 处置 |
| --- | --- | --- |
| 即时重写可能无限循环 | `_run_track` 重写触发逻辑 | `REWORK_MAX=1`（每次运行最多一轮即时重写）+ 超限回落行动项回路；`_settle_rework` 失败走 audit 留痕不阻塞 |
| 即时重写误伤普通打回 | gate 失败既有 `_review_retry` 路径 | 重构后：gate 失败无 rework 请求走原路径（extra_reason=""）；有 rework 请求走带留言理由的路径，两分支均有测试 |

## P2（低风险，接受）

| 问题 | 影响 | 处置 |
| --- | --- | --- |
| 即时重写仅覆盖「当前运行内、留言绑定当前轨」场景 | 跨轨/跨日/历史章节的重做仍走行动项 | 有意收敛，README 与评估文档已如实声明 |
| 记忆过滤可能漏掉跨类别相关记忆 | 如审稿的「会议」类记忆对 writer 不可见 | 映射表可配（`MEMORY_CATEGORY_MAP`），按需补类别；opinion 已对所有角色保留优先级 |
| memory_used 为可选字段 | 模型可能不输出，痕迹缺失 | 不强制 JSON（避免破坏正文/审稿输出），缺失默认空，不影响链路 |

## P3（文档与体验）

- README/evolution/自由度评估文档已同步（448 基线、R5 交付记录、差距清单补完进度）。
- memory_used 痕迹直接出现在 Agent 管理活动日志流中，未新增独立 UI；如需专门「记忆使用」卡片可后续增强。

## 影响评估表

| 步骤 | 改动面 | 影响的既有功能 | 回归证据 |
| --- | --- | --- | --- |
| R5-1 | config（REWORK_MAX）、editorial_daily（outbox 收集/写手注入/_run_track 触发/_settle_rework） | 消息决策回路、日更主产出、审稿打回 | 448+16 全绿；test_outbox/test_editorial_daily/test_review_retry 覆盖 |
| R5-2 | config（MEMORY_CATEGORY_MAP）、agent_context（角色过滤）、editorial_daily/agent_meeting/meeting_session（memory_used 提示与落库） | 注入快照、审稿/会议输出、活动日志 | 448+16 全绿；test_agent_context/test_editorial_daily/test_meeting_session 覆盖 |

## 结论

无 P0/P1 遗留；防循环、回落、降级路径均有测试与 audit 兜底。名实差距清单全部可修项已交付（a76bc3d / 8af3ae3 / 7cacc18），剩余两条为模型层面与设计红线，如实保留。
