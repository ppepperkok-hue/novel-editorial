# 去 n8n 迁移严格复审报告（2026-08-11 v4 · 收敛轮）

## 审查范围与方法

第四轮独立复审，聚焦前三轮未覆盖区域：Electron 桌面壳（main/preload/打包配置）、命令面板动作链、旧全自动路径（autopilot/novel_flow/publisher/scheduler）、dry-run 语义与落库行为、测试断言质量。

方法：静态扫描（桌面/前端/后端残留）→ 动作链末端走查（按钮 → API → handler → 副作用 → 刷新）→ 动态验证（dry-run 落库行为）→ 全量回归。

## 总评

本轮未发现 P0/P1。修复 2 个 P2（dry-run 假数据落库、命令面板周会假开关）与 2 个 P3（打包冗余、旧路径说明）。这是首轮「无严重问题」审查；修复后 259 后端 + 8 前端全绿。

## 问题清单

### P0 / P1（无）

### P2

1. **dry-run 把占位成功写入 `daily_runs`（假数据）**：`tools/editorial_daily.py` 在 `dry_run=True` 时仍 INSERT `running` 并 `_finish_run(completed, published=2)`，面板会显示一条「发布 2 章成功」的记录，看起来像真实发布。修复：`dry_run` 全程不写 `daily_runs`（含预检失败/异常路径）；`test_dry_run_full_chain_completed` 改为断言 0 行，`test_two_runs_are_idempotent` 同步断言不落库。
2. **命令面板周会暂停/恢复是假绿灯**：`CommandPalette` 的 `pause-weekly/resume-weekly` 调 `postControl({action:"pause", workflow:"weekly"})`，后端返回 `ok + note（无独立开关）`，前端却显示「操作成功：weekly 已暂停」。修复：移除周会开关命令；「立即更新一章」文案改为「立即补更（按当日章数，真实发布）」。

### P3

3. `desktop/package.json` extraResources 仍打包 `n8n/**`（n8n 已退役，`docs/legacy/` 有归档）。已移除。
4. `novel_pipeline/autopilot.py`、`novel_flow.py`、`publisher.py`、`scheduler.py` 为 n8n 时代全自动路径，当前无调用方（保留为后备，`install_daily_task.ps1` 已指向调度器）；与调度器共用同一把锁，回退时不会并发。记录不修。

## 确认无问题的模块

- 桌面托盘与命令面板的 `run_now` 动作链：全部走 `POST /api/control`，无 n8n 引用（打包配置除外，已修）。
- 调度器 dry-run 语义：占位全链可走通但不产生任何落库副作用（daily_runs/publish_logs/章节均不动）。
- 后端 259 测试 + 前端 8 测试 + build + `validate_workflow_deep.mjs` 全绿。

## 验证记录

- `python run_tests.py`：259 OK；`cd webapp && npm test`：8 OK；`npm run build` OK。
- 动态验证：dry-run 后 `daily_runs` 0 行；命令面板命令列表已无周会开关。
- 静态扫描：桌面/前端/后端无 `control.workflows` 或 n8n 功能引用残留。

## 修复记录

| # | 级别 | 修复 | 验证 |
| --- | --- | --- | --- |
| 1 | P2 | dry-run 不写 daily_runs（四路径统一） | `test_dry_run_full_chain_completed`/`test_two_runs_are_idempotent` 通过 |
| 2 | P2 | 移除命令面板周会假开关，修正日更按钮文案 | 前端 8 tests + build 通过 |
| 3 | P3 | 移除打包中的 n8n/** | build 通过 |

## 收敛判定

本轮为第一轮无 P0/P1 审查，P2 清零。按目标「直到不再审查出严重问题」，执行下一轮快速收敛审查（v5）确认无新 P0/P1/P2 后结束循环。
