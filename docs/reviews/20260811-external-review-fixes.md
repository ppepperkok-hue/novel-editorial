# 外部审查报告修复记录（2026-08-11）

来源：`20260811-strict-review.md`（基于 commit `e061d9c` 的独立审查，声称 v5
收敛结论不成立，提出 3 P1 + 8 P2 + 8 P3）。

处理原则：逐条对照当前代码验证，可复现的先写失败测试再修复；每条记录验证结果
（确认/部分确认/未复现）与修复状态。

## P1

### P1-1 多书并存串扰 —— 确认并修复

- `preflight.check_already_ran` 增加 `novel_id` 参数并按书过滤；调度器传入
  `ctx.novel_id`。
- `check_stock.check_stock(conn, novel_id)` 按书统计存稿并直接解析该书（不再
  只认 `publishing` 最新，顺带修复 finishing 作品存稿不可用）。
- `daily()` 一次解析 active novel 并贯穿预检/存稿/生成。
- 测试：`tests/test_book_isolation.py`（按书已发/按书存稿/finishing 可用）。

### P1-2 失败 LLM 调用成本不入账 —— 确认并修复

- `agent_tool_loop.run` 累计所有成功尝试的 usage，失败返回也携带
  `usage`/`model`（含 tool 轮失败、plain 轮失败、final 轮失败三个出口）。
- `editorial_daily._agent` 失败时同样写入 `ctx.costs`（真实 usage，可能为 0）。
- 测试：`test_failure_returns_usage_and_model`、`test_failed_agent_usage_is_recorded`。

### P1-3 发布链失败不可见 —— 确认并修复

- `_publish_track`：`new_article` 拒绝/未返回 item_id 时显式写
  `failed_nodes("发布A/B")` 与 `errors`（含平台 message）。
- `publish_article` 被拒（`published=False`）同样写 failed_nodes/errors。
- `record_work`：`reviewed` 且带 error 的章节也写 `publish_logs(failed)`。
- 测试：`test_publish_draft_rejection_is_visible`、
  `test_publish_rejection_writes_failed_log`。

## P2

### P2-1 质量门审稿全缺失放行 —— 确认并修复

`quality_gate`：逻辑审稿缺失或不可解析即不通过（错误「逻辑审稿缺失或不可解析」）；
读者/主编缺失仍按原降级语义。测试：`test_review_missing_or_unparseable_fails`。

### P2-2 运行锁 PID 检查 —— 确认并修复

`acquire_lock` 读锁文件 PID，`_pid_alive` 判定存活：PID 死亡立即回收（不再等
2 小时）；PID 存活即使超龄也不回收；旧格式/不可读按 2 小时兜底。测试：
`test_lock_recovered_when_pid_dead`、`test_lock_kept_when_pid_alive`。

### P2-3 桌面端口身份校验 —— 确认并修复

`desktop/main.js` 用 `apiReady()` 替代 TCP connect：连接后 GET `/api/control`
并校验响应含 `scheduler`，失败提示端口可能被其他服务占用。删除死代码
`portOpen`/`net` import。

### P2-4 取消会议语义 —— 文档如实化

README 改为「取消在轮次边界生效：当前发言会跑完（单次最长 300 秒），之后立即
停止」。实现本身（轮次边界检查）保留。

### P2-5 合规占位 —— 接入现役链路

`_run_track` 在质量门通过后调用 `compliance.check(editor_text)`，命中敏感词即
覆盖 gate 为不通过（错误「合规拦截：…」）。测试：
`test_compliance_hit_blocks_publish`（断言零发布调用、章节 draft、publish_logs
含合规拦截）。

### P2-6 daily_runs 孤儿恢复 —— 确认并修复

`daily_runs.recover_stale_runs(conn, stale_hours=6)` 把超时 `running` 标
`failed`（error「进程中断或超时（孤儿恢复）」）；`web_api.make_handler` 启动时
调用。测试：`test_recover_stale_runs`。

### P2-7 monitor 对 planning/finished 误报 —— 确认并修复

`monitor.run_checks` 只遍历 `publishing`/`finishing` 作品。测试：
`test_planning_and_finished_books_do_not_warn`、
`test_publishing_book_with_empty_stock_warns`；同步更新
`test_autopilot.test_daily_run_warns_when_backlog_below_safe_line`（预置连载书）。

### P2-8 死代码与多套发布实现 —— 标注 deprecated

`autopilot.py`/`novel_flow.py`/`pipeline.py`/`desktop.py` 模块与
`publisher.FanqieHttpAdapter`、`scheduler.Scheduler` 类 docstring 标注
DEPRECATED（保留为回退后备；monitor 仍使用 `SAFE_BACKLOG`/`backlog_level`）。

## P3

1. README 测试数 250 → 259（3 处）。
2. dry-run 全离线：`_preflight` 在 dry_run 时跳过 `check_cookie`。测试：
   `test_dry_run_skips_cookie_probe`。
3. web_api 参数解析安全化：所有 `int(qs[...])`/`int(qs.get(...))`/
   `int(payload.get(...))` 改为 `_parse_int`（非数字取默认值，不再 500）。
   测试：`test_bad_query_params_do_not_500`。
4. `desktop/release.js` 代理改读 `HTTPS_PROXY`/`HTTP_PROXY` 环境变量，不再
   硬编码 127.0.0.1:7897。
5. SSE 并发连接上限 8（超出 503），连接关闭时计数释放。
6. `knowledge.write_knowledge` 拒绝 frontmatter 字段含换行（title/source/
   updated_at）。测试：`test_write_rejects_newline_in_frontmatter`。
7. `install_daily_task.ps1` 优先 `$env:PYTHON_EXE`，其次 `Get-Command python`。
8. `desktop/package.json` extraResources 移除 `demo.db` 与 `docs/**`，避免
   本机构建携带真实数据。

## 验证记录

- `python run_tests.py`：276 OK（259 + 17 新增）。
- `cd webapp && npm test`：8 OK；`npm run build` OK。
- `node tools/validate_workflow_deep.mjs`：OK（未改工作流）。
- 外部报告的 3 个 P1 全部确认并修复；8 个 P2 全部处理（4 修复 + 1 文档如实 +
  1 接入 + 1 恢复机制 + 1 标注）；8 个 P3 全部处理。
