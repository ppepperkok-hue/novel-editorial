# 后补项目清单（Parked Backlog）

- 建立：2026-08-20（N9 收口时，总监整理）
- 定位：从 [06-new-capability-backlog.md](06-new-capability-backlog.md) 主清单与各实施文档「暂不做」节汇总的**后置 / 未立项**能力项；不重复定义需求（需求以 06 为准），只记录状态、依赖与来源，供后续按依赖与用户取舍取用。
- 规则：每项立项时新建 `docs/implementation/m5-*.md` 实施文档，走完整流程；本清单在该项收口后移入 06 状态（或直接删除该行）。

## 待立项能力项（截至 2026-08-22）

无（06 清单 N1–N26 全项收官，N12 图形面板已于 2026-08-22 按完整流程收口）。

## 工程小待办（非能力项）

| 事项 | 级别 | 来源 |
| --- | --- | --- |
| ruff format 对个别旧文件的既有格式遗留（验收只要求 ruff check） | P3 | progress-summary「已留档的待办项」 |
| N10 O1 初始审查报告未单独归档（结论并入 20260820-M5N10O2-initial.md 说明） | 记录 | docs/reviews/20260820-M5N10O2-initial.md |
| API 层 talk / draft / style 编排胶水与 cli 层重复（应下沉 core，待 S3 动 core/draft 时合并） | P3 | FE-W1 S1 总监记录 |
| CLI `talk send` 允许空消息，与 API 空白校验不同源（建议 CLI 同步为用法错误） | P3 | FE-W1 S1 修复偏离点 |
| CLI `draft list` / `draft show` 对 writer_id 为空的作者稿回退显示默认写手名（应显示「作者」） | P3 | FE-W1 S3a 收口记录 |
| API 的 inspect / workspace_log 两个 text/plain 端点缺 response_class 声明（OpenAPI 记成 application/json），待统一补齐 | P3 | FE-W1 S4a 修复偏离点 |
| w1_demo / w2_demo / panel_demo 的 _prepare_env 只清 NOVEL_LLM_*，其余 NOVEL_* 会漏入演示（w3_demo 已在 FE-W3 S3 修复） | P3 | docs/reviews/20260828-FE-W3-S3-initial.md |

2026-08-22 收口：`core/behavior.py` 空 kind 守卫 / style 只读访问器（含 style_drift 统一）/ 归档 0 字节 SQLite 探针 三项 P3 已随 commit 3139c81 完成，独立审查通过（docs/reviews/20260822-M9ENG1-initial.md），文档同步后从本表移除。

## 明确不做边界（引用 06，不展开）

自动发布到外部平台、成本核算中心、多作者实时共编、一键全自动流水线、强制流程关卡与固定晨会；多语言文档与桌面安装器随 N11/N12 需要再议。详见 06 主清单。

## 取用顺序与收口状态

1. N12（依赖 N10 已满足，但用户明确后置）——06 清单唯一剩余项。
2. 2026-08-22 收口：N12 图形面板已按完整流程完成，06 清单 N1–N26 全项收官；本清单已无待立项能力项。
