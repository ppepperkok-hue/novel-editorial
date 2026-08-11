# 去 n8n 迁移审查报告（2026-08-11）

## 审查范围与方法

本次审查覆盖去 n8n 迁移的全部改动：`tools/editorial_daily.py`（调度器）、`tools/editorial_steps.py`（节点逻辑复刻）、`tools/flow_graph.py` / `tools/export_flow_html.py`（链路可视化）、`tools/daily_runs.py`（本地留痕与 legacy 同步）、`novel_pipeline/services/control.py`（控制层去 n8n）、`novel_pipeline/web_api.py`（executions/flow/export 端点）、`scripts/install_daily_task.ps1` / `install_autostart.ps1` / `watch_daily.py`（触发与自启）、前端 `DashboardPage/ExecutionsPage/FlowPage/Shell/App`。

执行：全量测试与构建基线 → `rg` 静态扫描（裸异常/硬编码路径/密钥/静默失败/测试隔离）→ 分域人工走查（逻辑边界/数据层/并发/外部集成/安全/产物/前端/可观测性/性能/测试交付）→ 修复后复验。

## 总评

骨架健康：66 节点 n8n 编排壳已等价迁移到单入口 Python 调度器，业务全部进程内复用既有工具，补偿逻辑（K1–K10）逐条保留并有测试锚定；面板不再依赖 n8n 在线，运行留痕本地化，链路可视化可离线审查。未发现 P0/P1；3 处 P2/P3 已在审查中修复，另记录 4 项观察项。

## 问题清单

### P0（无）

### P1（无）

### P2

1. `scripts/watch_daily.py` 原第 12 行硬编码 `DB = r"E:\code\novel-pipeline\demo.db"`，换机即失效。**已修复**：改为 `ROOT / "demo.db"`，同时去掉对 n8n execution_entity 与 `N8N_API_KEY` 的依赖，改读 `daily_runs`。

### P3

2. `novel_pipeline/services/control.py` 的 `apply_schedule` 原用 `config.DB_PATH.name` 传给计划任务脚本，数据库若位于子目录会丢失路径层级。**已修复**：改用 `os.path.relpath(config.DB_PATH, ROOT)`。
3. `webapp/src/components/FlowPage.jsx` 导出链接原为绝对 `/api/export/flow`，`file://` 直开面板时会指向本地文件根路径。**已修复**：拼接与 `api.js` 一致的 `API_BASE`。

### 观察项（有意保留，记录不修）

4. `tools/check_stock.py` 只认 `status='publishing'` 的作品，`finishing`（收尾中）作品的存稿不会走「发存稿」分支。此为 n8n 原语义，本阶段保持忠实；列入初心接续路线「完结机制」一并处理。
5. 面板「执行记录」表已切换为 `daily_runs`（周会执行不再出现在该表）；周会进度改由会议中心/`weekly_meetings` 呈现，属预期。
6. `services/control.py` 在非 Windows 上 `apply_schedule` 仅保存定时设置并显式返回降级说明。
7. n8n 遗留代码（`services/n8n.py`、`render_workflow.py`、`N8N_*` 环境变量、`n8n/novel_workflow.json`）有意保留为回退路径；`docs/legacy/` 已归档工作流 JSON 副本，回退时可 `scripts/start_n8n.ps1` 手动启动。

## 确认无问题的模块

- 调度器状态机与锁：`daily()` 在预检前写 `running`，所有退出路径（成功/失败/异常/跳过）都有终结或清理；锁与 n8n 共用 `n8n_tmp/<db>.lock`，原子创建 + 2h 陈旧回收 + finally 释放；scheduled 关闭时删除占位行不产生死记录。
- A/B 隔离与补偿：质量门失败只短路该轨；K2/K5 补位与 n8n `汇总运行结果` 逐字对齐，`build_payload` 测试覆盖四态与补位。
- 外部集成：番茄发布字段与 n8n bodyParameters 完全一致（new_article/cover_article/publish_article/modify_book/chapter_list）；错误显式落 `failed_nodes`/`errors`/`publish_logs`。
- 安全：扫描未见硬编码密钥；Cookie/CSRF/Token 全部走 env；测试用临时库 + mock，不触真实网络/n8n/番茄。
- 前端：所有新显示字段均有后端出处（`/api/flow`、`/api/control`、`/api/daily_runs`）；链路视图有空态/错误态；危险操作（暂停/补更）有确认框。

## 验证记录

- `python run_tests.py`：250 tests OK（243 旧 + 7 新：flow_graph 4 + export_flow_html 3；另 editorial_steps 30 + editorial_daily 8 已计入 243 增量）。
- `cd webapp && npm test`：8 tests OK；`npm run build` 成功。
- `node tools/validate_workflow_deep.mjs`：OK（n8n 工作流文件未改动）。
- 动态验证：dry-run 全链（mock preflight + 临时库）→ `completed`、发布 2 章、`daily_runs.source='scheduler'`；锁并发 → 第二个运行被拦；A 轨质量门失败 → `partial`、A 章 draft、B 章 published。
- 退役验证：n8n 主进程与 task-runner 已停止（`N8N_OFFLINE`）；启动文件夹仅剩 `NovelPipeline-api.vbs`；`docs/legacy/novel_workflow.json`（121,745 B）与 `architect_weekly.json` 已归档。

## 后续建议

- 真实运行观察 1–2 周后再删除 n8n 数据（`~/.n8n`）与遗留代码；期间若回退，直接 `scripts/start_n8n.ps1` 启动即可。
- 初心接续路线按序推进：编辑部人格化（mailroom/记忆/关系）→ 审稿打回重写（调度器内建回环）→ 完结机制（顺带修复观察项 4）→ 统一留痕 → 人物卡进化。

## 修复记录

| # | 级别 | 修复 | 验证 |
| --- | --- | --- | --- |
| 1 | P2 | watch_daily 去硬编码路径并改读 daily_runs | 全量回归通过 |
| 2 | P3 | apply_schedule 用 relpath 传库路径 | 全量回归通过 |
| 3 | P3 | FlowPage 导出链接兼容 file:// | 前端构建通过 |
