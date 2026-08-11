# 去 n8n 迁移严格复审报告（2026-08-11 v5 · 收敛确认）

## 审查范围与方法

第五轮收敛审查。范围：全前端控制动作链（每个 `postControl` action → `handle_control` 分支逐项核对）、全部 API 端点清单、v3/v4 改动回归（dry-run 落库行为、审稿失败中断、pending_publish 消费、周会锁、快照去 n8n）、真实 API 冒烟。

方法：基线（后端 259 + 前端 8 + build）→ 动作链全覆盖核对 → API 动态冒烟 → 分域复核 v3/v4 修复点。

## 总评

本轮**未发现 P0/P1/P2**。前端所有控制动作（run_now daily/weekly、pause/resume daily、save_settings、apply_schedule、run_knowledge_keeper、refresh_hot_topics）在后端均有对应 handler 且副作用正确；v3/v4 修复点全部有测试锚定并保持全绿；真实 API 响应正常。审查循环收敛。

## 确认清单

### 动作链全覆盖（无假绿灯、无死按钮）

| 前端动作 | 后端 handler | 副作用 | 状态 |
| --- | --- | --- | --- |
| run_now daily（含 chapters） | `handle_control` → 后台线程 `editorial_daily.daily` | 写 daily_runs/发布 | ✓ |
| run_now weekly | → `_weekly_worker`（weekly.lock 防重入） | 热点→周会→蒸馏 | ✓ |
| pause/resume daily | → `daily_enabled` 开关 | settings 落库 | ✓ |
| save_settings | → 白名单写 settings | settings 落库 | ✓ |
| apply_schedule | → Windows 计划任务注册 | settings + 计划任务 | ✓ |
| run_knowledge_keeper | → `knowledge_keeper.run` | 知识包/草案 | ✓（同步执行，P3 已记录） |
| refresh_hot_topics | → `hot_topics.refresh` | 热点文件 + audit | ✓ |

### 修复点回归确认

- dry-run 不写 `daily_runs`（v4）：测试断言 0 行，通过。
- 审稿失败中断该轨（v3）：`test_reviewer_failure_blocks_track_publish` 通过。
- `pending_publish` 一次性消费（v3）：`test_pending_publish_is_consumed_after_generate` 通过。
- 周会防重入锁（v2）：`test_weekly_worker_skips_when_lock_held`/`releases_lock` 通过。
- SSE 快照无 n8n（v2）：`test_build_snapshot_uses_local_runs_without_n8n` 通过；alerts.log 无新增 n8n 噪音。
- HTML 报告转义（v2）：`test_error_content_is_html_escaped` 通过。

### 动态验证

- `GET /api/control` 200（scheduler 结构）；`GET /api/flow` 200（35 nodes）；`GET /api/daily_runs?limit=2` 200。
- 基线：259 后端 + 8 前端 + `npm run build` + `validate_workflow_deep.mjs` 全绿。

## 遗留观察项（非严重，有意保留）

1. `daily_runs.sync_from_n8n` 与 `services/n8n.py` 保留为回退观察期兼容（观察结束后移除）。
2. `autopilot/novel_flow/publisher/scheduler` 旧全自动路径为无调用方后备（与调度器共用锁，回退安全）。
3. `run_knowledge_keeper`/`refresh_hot_topics` 同步执行阻塞单个 HTTP 线程（ThreadingHTTPServer 多线程，不影响其他请求）。
4. 备份失败仅告警不阻塞（发布链有留痕兜底）。

## 结论

自 v3 起连续两轮（v4/v5）无 P0/P1，v5 连 P2 也未发现；所有已发现问题均已修复并有测试锚定。按目标「直到不再审查出严重问题」，审查循环收敛。
