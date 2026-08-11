# 去 n8n 迁移严格复审报告（2026-08-11 v3）

## 审查范围与方法

独立第三轮复审，不沿用前两轮结论。范围：调度器 `tools/editorial_daily.py` 全文（920 行逐段走查）、`tools/editorial_steps.py`、`tools/daily_runs.py`、控制层 `novel_editorial/services/control.py`、`agents.py`、`web_api.py`、全部前端页面（重点 SettingsPage/AgentsPage/FlowPage 的旧结构残留），以及测试断言质量。

方法：基线（259+8 全绿）→ 静态扫描（n8n 残留/裸异常/硬编码/密钥/TODO/死 import）→ 分域走查 → 动态验证（失败测试先行复现 2 个 P1，再修复；API 真实响应验证）。

## 总评

本轮发现并修复 **4 个 P1**（其中 2 个为调度器语义漂移、2 个为前端假动作/旧结构残留），以及若干 P2/P3。前两轮未覆盖到的「审稿失败可能放行发布」与「手动章数永久抬高每日目标」是本轮最重要发现；两者均先以失败测试复现再修复。修复后 259 后端 + 8 前端全绿。

## 问题清单

### P1

1. **审稿 agent 失败会放行该轨发布**：`tools/editorial_daily.py:_run_track` 中 `审稿A/B` 调用失败时 `review_text=None`，随后质量门在 `review=None` 且 `editor=None` 时走 `else: True` 降级路径，导致**未经逻辑审稿的章节可能被发布**。n8n 原语义：审稿节点失败会走错误分支，质量门根本不执行、该轨不发布（读者/主编失败才降级，因为质量门内用 try/catch 包裹读取）。动态验证：mock 审稿A 失败 → 实测 A 章仍发布（published=2）。修复：审稿失败即返回 `gate.passed=False`（errors=`审稿链路失败：审稿A/B`），不再调用读者/终审/提炼；`test_reviewer_failure_blocks_track_publish` 锚定（A 轨 draft + 不发布 + 后续 agent 不调用）。
2. **手动指定章数永久抬高每日目标**：`run_now` 写 `pending_publish=N`，但现造路径结束后从不消费，次日定时仍按 N 章目标运行（n8n 继承的历史缺陷）。动态验证：`daily(chapters=3)` 后 `settings.pending_publish` 仍为 `"3"`。修复：`daily()` 在 `check_stock` 之后无条件清零 `pending_publish`（一次性目标语义）；`test_pending_publish_is_consumed_after_generate` 锚定。
3. **AgentsPage「部署到 n8n」是假绿灯**：前端部署按钮调 `agent_deploy` → `control.deploy_workflow`（no-op 返回 ok），但 UI 文案显示「已部署到 n8n（N 节点，运行中）」。n8n 已退役，这是「看起来成功、什么都没发生」的最高优先 bug。修复：删除部署按钮、确认弹窗与 `deploy()` 函数；保存按钮语义改为「保存并校验，调度器运行时即时生效」。
4. **SettingsPage 工作流卡片仍读旧 `control.workflows`**：n8n 退役后 `load_control` 返回 `scheduler`，设置页三张卡片（日更/周会/知识管家）全部显示「n8n 离线」，且状态文案引用不存在的 `wfs.daily.active`。修复：改为调度器状态卡（日更开关 + 上次运行 + 定时时间），周会/知识管家改为手动触发按钮；同时清理确认弹窗三态与「部署到 n8n」文案。

### P2

5. **`_get_meta` 超时错误分类不精确**：`tools/editorial_daily.py` 只捕获 `OSError/ValueError`，`subprocess.TimeoutExpired`（属 `SubprocessError`）会冒泡成「调度器异常」而非「读本地资料」失败节点。修复：捕获 `subprocess.SubprocessError`。
6. **Agent 资产校验文案硬编码节点数**：`AgentsPage` 保存成功日志写死「56 节点」（实际 66），数字漂移。修复：去掉数字。

### P3

7. `novel_editorial/services/agents.py` 残留 `from novel_editorial.services import n8n` 死 import（无任何使用）。已删除。
8. 备份失败仅记 warning 不阻塞（与 n8n「备份失败即停」语义不同）；设定知识库初始化失败同样不阻塞。属工程取舍（发布链已有 publish_logs/daily_runs 留痕），记录不修。
9. `run_knowledge_keeper`/`refresh_hot_topics` 为同步执行，长任务会阻塞 HTTP 请求线程（ThreadingHTTPServer 多线程，不阻塞其他请求）；体验优化留给后续。

## 确认无问题的模块

- 调度器锁/四态/A-B 隔离/K2-K5 补偿（前两轮测试仍全绿，本轮新增 2 个 P1 回归测试）。
- 番茄发布字段与失败显式化（逐字段核对无变化）。
- `web_api` POST 白名单与 Origin 校验、`/api/export/flow` 与 `/api/flow` 真实响应（35 节点/36 边/HTML 9146B）。
- 无裸 `except:`、无硬编码密钥、无 TODO/FIXME 残留（本轮扫描）。

## 验证记录

- 基线：259 后端 + 8 前端 + build + `validate_workflow_deep.mjs` 全绿。
- 动态复现：`test_pending_publish_is_consumed_after_generate` 修复前 FAIL（target 残留 3）、`test_reviewer_failure_blocks_track_publish` 修复前 FAIL（published=2 而非 1）；修复后均通过。
- API 动态验证：`/api/flow` 200（35 nodes/36 edges）、`/api/daily_runs?limit=3` 200、`/api/export/flow` 200（text/html，9146 B）。
- 静态扫描：全前端 `workflows|n8n` 残留清零（仅测试 mock 保留旧结构数据，无功能引用）。

## 修复记录

| # | 级别 | 修复 | 验证 |
| --- | --- | --- | --- |
| 1 | P1 | 审稿失败即中断该轨（gate.passed=False），不发布不降级 | `test_reviewer_failure_blocks_track_publish` 通过 |
| 2 | P1 | `daily()` 在 check_stock 后清零 `pending_publish` | `test_pending_publish_is_consumed_after_generate` 通过 |
| 3 | P1 | 删除 AgentsPage 假部署动作与按钮 | 前端 8 tests + build 通过 |
| 4 | P1 | SettingsPage 卡片改读 `scheduler`，周会/知识管家改手动触发 | 前端 8 tests + build 通过 |
| 5 | P2 | `_get_meta` 捕获 `SubprocessError` | 全量回归通过 |
| 6 | P2 | 去掉硬编码节点数文案 | 前端 build 通过 |
| 7 | P3 | 删除 agents.py 死 import | 全量回归通过 |

## 收敛判定

本轮 4 个 P1 全部清零并锚定；P2 全部修复；P3 仅剩 3 条观察项（有意保留）。下一轮复审将确认无新 P0/P1/P2 且前端无残留后结束循环。
