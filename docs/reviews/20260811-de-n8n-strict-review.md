# 去 n8n 迁移严格复审报告（2026-08-11 v2）

## 审查范围与方法

本次为独立复审，不沿用上一轮结论。范围：迁移核心 `tools/editorial_daily.py`、`tools/editorial_steps.py`、`tools/flow_graph.py`、`tools/export_flow_html.py`、`tools/daily_runs.py`，控制层 `novel_editorial/services/control.py`、`novel_editorial/web_api.py`（含 SSE 快照线程）、`scripts/*.ps1`、`scripts/watch_daily.py`，前端 `DashboardPage/ExecutionsPage/FlowPage/Shell/App`，以及迁移涉及的既有工具（publish_stock/record_work/check_stock/current_book/collect_reader_stats）与全部相关测试。

方法：基线（后端 251 + 前端 8 + build + validate 全绿）→ 静态扫描（裸异常/硬编码/密钥/残留 n8n 调用/未转义 HTML/测试外部依赖）→ 分域走查（逻辑/数据/并发/外部/安全/生成物/前端/可观测/性能/测试）→ 动态验证（构造失败与并发场景）。

## 总评

主链路与上一轮结论一致：调度器状态机、A/B 隔离、K2/K5 补偿、番茄字段对齐均有测试锚定，未发现 P0。但本轮独立走查发现 **1 处 P1 运行路径残留（SSE 快照线程仍调 n8n）、1 处 P1 并发缺陷（周会无防重入锁）、1 处 P1 测试隔离违规**，以及 HTML 注入面、异常路径丢发布统计等 P2/P3，均需修复。

## 问题清单

### P1

1. **SSE 快照线程仍调用 n8n API**：`novel_editorial/web_api.py:61-64` 的 `_snapshot_loop` 每 5 秒执行 `n8n_service.workflow_status(...)` 与 `n8n_service.executions()`。n8n 已停止，实测 `alerts.log` 在 18:47–18:48 连续写入「n8n API GET /executions... 失败」「n8n API GET /workflows... 失败」（共 3+ 条/轮）。影响：日志噪音、无用网络依赖、快照线程与「去 n8n」目标相悖；`workflows` 字段已无前端消费者（前端改读 `scheduler`）。修复：快照 `executions` 改读 `daily_runs.local_executions(conn)[:5]`，删除 `workflows` 字段。
2. **周会后台触发无防重入锁**：`novel_editorial/services/control.py:_background_weekly` 直接 `_spawn(worker)`，连续点击「立即开会」会并行启动多个周会线程，同时跑 `agent_meeting.py`（20–50 分钟、flash 调用约 20–40 次），成本翻倍且周会档案可能互相覆盖。日更路径有 `preflight` 原子锁，周会没有。修复：worker 复用 `preflight.acquire_lock/release_lock` 持有 `n8n_tmp/weekly.lock`，拿不到锁则告警并跳过。
3. **测试隔离违规**：`tests/test_editorial_daily.py` 的 `test_track_isolation_quality_gate_failure` 与 `test_real_chain_records_chapters_and_costs` 以 `dry_run=False` 跑 `daily()`，但未 mock `_wrapup`，会真实执行 `collect_reader_stats.run`（番茄网络请求）、`write_diaries.write` 与 `auto_fill_actions.run`（LLM 调用）。当前因环境无凭据快速失败而“通过”，属被容错掩盖的外部依赖，违反测试隔离红线。修复：两个用例显式 mock `tools.editorial_daily._wrapup`。

### P2

4. **自包含 HTML 报告存在 HTML 注入面**：`tools/export_flow_html.py:69-72`（`summary`、`error`）与报告头部的数据库内容直接 f-string 插入 HTML，未转义。`last_run.error` 可能包含 Agent 输出中的 `<...>` 片段，本地打开报告时可注入任意 HTML（含 script 引入的有限风险）。修复：`html.escape` 所有插入点，并加「error 含 `<script>` 时输出被转义」的测试。
5. **调度器异常路径丢失已发布统计**：`tools/editorial_daily.py:893-896` 外层 `except` 无条件 `_finish_run(..., "failed", 0, ...)` 且返回 `published: 0`。若异常发生在 A 轨已发布之后（如 `build_payload`/写 `daily_result.json` 阶段），`daily_runs.published` 与返回值会把已发布章记为 0。修复：`_Ctx` 增加 `published` 计数器，`_publish_track` 成功时累加、存稿路径回填，异常路径使用 `ctx.published`。
6. **`limit` 参数无边界防御**：`tools/daily_runs.py` 的 `list_runs`/`local_executions` 对 `limit` 未做 clamp，`/api/daily_runs?limit=-1` 会退化为 SQL `LIMIT -1`（全表返回）。本地小表风险低，但缺防御。修复：clamp 到 `[1, 500]`。

### P3

7. `/api/daily_runs` 每次请求惰性 `sync_from_n8n` 直连 `~/.n8n/database.sqlite`（`tools/daily_runs.py:38-55`）。n8n 已退役，历史同步属有意保留；但面板 30s 轮询会持续读旧库。建议观察期结束后移除 legacy 同步，本轮仅记录。
8. 前端 `FlowPage.jsx` 的 `GROUP_X/GROUP_LABEL` 与后端 `tools/flow_graph.py` 重复维护，新增节点组时可能布局漂移。本轮不修，记录为文档约束。
9. `tests/test_daily_runs.py` 的 `sync_from_n8n` 用例未断言 `source='n8n-legacy'`，迁移语义无测试锚定。本轮补一条断言。

## 确认无问题的模块

- 调度器锁与四态：`daily()` 预检前写 `running`，成功/失败/跳过均有终结；与 n8n 共用锁、2h 陈旧回收、finally 释放；锁并发测试通过。
- A/B 隔离与补偿：质量门失败只短路该轨；K2/K5 与 n8n `汇总运行结果` 逐字对齐并有测试。
- 外部集成：番茄发布/建书/作品资料字段与 n8n bodyParameters 逐字段一致；失败显式落 `failed_nodes`/`publish_logs`。
- 安全基线：无硬编码密钥（扫描）；Cookie/CSRF/Token 全走 env；POST 白名单 + Origin 校验不变。
- 前端数据出处：FlowPage/仪表盘/执行记录所有新字段均有后端接口出处；空态/错误态齐全。
- 报告自包含：无外部 CDN/脚本引用（测试断言），除上述 HTML 转义问题外无外部依赖。

## 验证记录

- 基线：`python run_tests.py` 251 OK；`cd webapp && npm test` 8 OK；`npm run build` OK；`node tools/validate_workflow_deep.mjs` OK。
- 静态扫描：裸异常均为 `except Exception: # noqa: BLE001` 且带显式处理；硬编码路径仅剩 `scripts/watch_daily.py`（已在上轮修复，本轮复扫未见）；密钥无硬编码。
- 动态证据：`alerts.log` 中 n8n 失败日志与 `web_api.py:61-64` 直接对应；`_background_weekly` 无锁路径在代码走查确认；dry_run=False 测试未 mock `_wrapup` 由 `rg` 确认。

## 后续建议

- 修复优先序：P1 三条 → P2 三条 → P3 测试锚点；修复后全量回归并把验证结果登记到本报告「修复记录」。
- 观察期（1–2 周）结束后移除 `sync_from_n8n`、`services/n8n.py` 与 `N8N_*` 配置项。

## 修复记录

| # | 级别 | 修复 | 验证 |
| --- | --- | --- | --- |
| 1 | P1 | `_snapshot_loop` 改用 `_build_snapshot(conn)`（executions 读 `daily_runs.local_executions`），删除 `workflows` 字段与 `n8n_service` import | `test_build_snapshot_uses_local_runs_without_n8n` 通过；alerts.log 不再出现 n8n 失败噪音 |
| 2 | P1 | 周会触发抽 `_weekly_worker()`，持 `n8n_tmp/weekly.lock`（preflight 原子锁 + 陈旧回收），拿不到锁告警跳过 | `test_weekly_worker_skips_when_lock_held`、`test_weekly_worker_releases_lock` 通过 |
| 3 | P1 | 两个 `dry_run=False` 测试显式 mock `_wrapup`，不再触碰真实网络/LLM | 测试在无凭据环境下快速稳定通过 |
| 4 | P2 | `export_flow_html` 对 `summary`/`error` 做 `html.escape` | `test_error_content_is_html_escaped` 通过 |
| 5 | P2 | `_Ctx.published` 计数器：发布成功累加、存稿路径回填、异常路径使用真实计数 | `test_exception_after_publish_keeps_published_count` 通过（异常后 published=2 仍落库） |
| 6 | P2 | `list_runs`/`local_executions` 的 `limit` clamp 到 `[1,500]` | `test_limit_is_clamped` 通过 |
| 9 | P3 | `test_sync_persists_and_is_idempotent` 增加 `source='n8n-legacy'` 断言 | 通过 |

修复后全量：后端 **257 tests OK**（251 + 6 新增）、前端 8 tests + build OK、`validate_workflow_deep.mjs` OK。无引入新问题（相关 44 个用例单独跑也全绿）。
