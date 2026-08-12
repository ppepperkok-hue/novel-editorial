The review is complete. Below is the final report.

## 审查范围 (Scope)

- **审查路径（27 个文件）**：`tools/editorial_daily.py`、`workday.py`、`editorial_steps.py`、`editorial_state.py`、`flow_graph.py`、`export_flow_html.py`、`daily_runs.py`、`auto_fill_actions.py`、`agent_context.py`、`agent_meeting.py`、`agent_tool_loop.py`、`mailroom.py`、`relations.py`、`promises.py`、`meeting_actions.py`、`meeting_kinds.py`、`meeting_materials.py`、`meeting_free_loop.py`、`meeting_executor.py`、`meeting_speaker.py`、`meeting_mentions.py`、`meeting_interactions.py`、`meeting_events.py`、`write_diaries.py`、`architect_weekly.py`、`apply_architect.py`、`app_settings.py`
- **依赖契约核验**（仅验证接口）：`novel_editorial/db.py`、`config.py`、`llm_client.py`、`services/{activity,audit,agency,knowledge,meeting_session}.py`、`tools/{producers,preflight,check_stock,publish_stock,current_book,record_work,novel_knowledge,backup,collect_reader_stats}.py`

## 基线结果 (Baseline)

| 验证项 | 结果 |
|---|---|
| `python -m compileall`（27 个切片文件） | ✅ COMPILE_OK |
| `tests/test_workday.py` | ✅ 13 passed |
| `tests/test_meeting_free_loop.py` + `test_meeting_free_e2e.py` | ✅ 16 passed |
| `test_editorial_daily.py` + `test_daily_runs.py` + `test_meeting_actions.py` + `test_apply_architect.py` + `test_auto_fill_actions.py` + `test_promises.py` | ✅ 63 passed |
| `editorial_daily.py --dry-run --chapters 2`（含 publishing 书） | ✅ completed, published=2 |
| `export_flow_html.py`（demo.db 副本） | ✅ 输出 10007 bytes |
| `workday.py --action open --dry-run` | ✅ 走到 awaiting_close |

## 发现 (Findings)

### [P2] 预检跳过的工作日会被 close 错误标记为 completed（假绿灯）
**文件**：`tools/workday.py:392-403`
**证据**：`_close_locked` 中 `produce_status in ("completed", "skipped")` 一律映射到 `final_status = "completed"`。复现：构造 `status='skipped', phase='awaiting_close', error='日更已暂停…'` 的 workday 行后调用 `workday.close(dry_run=True)`，返回 `{'ok': True, 'status': 'completed', 'published': 0}`。当 `editorial_daily._finish_run` 因预检跳过（如 `daily_enabled=false` 的定时触发）写入 `status='skipped'` 后，`workday.open` 继续走到 awaiting_close，`close()` 将其改写为 `completed`，面板与 `export_flow_html` 均显示"上次成功"，实际当天零产出。`daily()` 自身刻意区分 skipped 与 completed，此处却将其合并。
**建议**：`skipped` 应作为终态保留（`final_status = "skipped"` 或至少不覆盖）。

### [P2] 自由会议冷启动发言不刷新 heartbeat，安静 60 分钟后会话被误杀
**文件**：`tools/meeting_free_loop.py:131-146`
**证据**：free 模式下唯一写 `meeting_sessions.heartbeat_at` 的地方是 `_process_event`（line 108）；`_process_cold` 与 `_speak`（agent 发言落库）都不触碰 heartbeat。冷定时器（默认 30s）会让 agent 持续发言，但用户超过 60 分钟不发消息时，`meeting_session.get_active_session`（`novel_editorial/services/meeting_session.py:120-140`）与 `web_api._fail_orphan_sessions`（`web_api.py:1267-1281`）把该 running 会话标记为 `failed`，之后 `submit_event` 的事件在 `_process_event` 中被静默丢弃（status 非 running 直接 return），会议在无任何告警下死亡。
**建议**：冷启动发言/agent 发言时同步刷新 heartbeat，或将 liveness 与 loop 线程状态挂钩。

### [P3] 自由会议 worker 线程无异常兜底，LLM 压缩失败会静默杀死事件循环
**文件**：`tools/meeting_free_loop.py:86-102`
**证据**：`_run_worker` 对 `_process_event`/`_process_cold` 无 try/except。`_maybe_compress` → `meeting_executor.summarize_history` → `agent_meeting.ask` → `_chat_with_retry` 在 3 次重试后抛 `RuntimeError`，异常直接击穿 daemon worker（无 audit 记录、无告警），被消费的该条事件丢失；会话停留在 `running` 直到 60 分钟超时回收。与文件头"Failures are explicit / fail-closed"的既定契约不符。
**建议**：对单事件处理加异常兜底，记录 audit 后继续排空队列。

### [P3] 存稿发布分支的失败详情被丢弃，无法在链路图上高亮
**文件**：`tools/editorial_daily.py:1819-1828`
**证据**：`publish_stock.publish_batch` 返回 `{target, published, failures, warnings}`，不含 `ok`/`error` 键，因此 `if not result.get("ok") and result.get("error")` 恒为假（死代码），`_run_tool` 的 `ok is False` 检查也不会触发：单章发布失败（HTTP 错误等）既不进 `ctx.failed_nodes` 也不进 `ctx.errors`/warnings。运行总状态仍由 `published` 计数推导（partial/failed 正确），但 `flow_graph` 无法标红"发布存稿"节点，错误文本为空。
**建议**：依据 `failures`/`warnings` 非空回填 `failed_nodes` 与错误详情。

### [P3] workday 的 dry-run 仍会写数据库和锁文件
**文件**：`tools/workday.py:179`
**证据**：`open(..., dry_run=True)` 在 dry_run 守卫之前无条件调用 `_recover_stale_open(conn)`，该函数会 UPDATE `daily_runs`（把超时中的旧行标 failed）并写 audit；同时 `preflight.acquire_lock` 会创建 `n8n_tmp/*.lock`。与本仓库其余 dry-run"不落任何库"的约定不一致，一次 dry-run 可能永久改写真实数据。
**建议**：dry_run 时跳过 `_recover_stale_open`（或仅读取报告）。

## 影响表 (Impact Table)

| # | 优先级 | 影响面 | 触发条件 | 后果 |
|---|---|---|---|---|
| F1 | P2 | daily_runs 状态/面板/HTML 报告 | scheduled 触发 + daily_enabled=false 的 workday | 零产出日显示"上次成功"，ok=True |
| F2 | P2 | 自由会议会话生命周期 | 用户 >60 分钟不发言 | 会话被误标 failed，后续事件静默丢弃 |
| F3 | P3 | 自由会议可靠性 | LLM 持续失败触发压缩 | worker 静默死亡、事件丢失 |
| F4 | P3 | 存稿发布诊断 | 单章发布失败 | 链路图不标红、无错误详情 |
| F5 | P3 | dry-run 语义 | 存在陈旧 workday 行时执行 dry-run | 真实行被标记 failed |

## 结论 (Conclusion)

**总体判定：patch 基本正确（无 P0/P1 阻断性问题）**。语法、契约与切片相关 92 个测试全部通过，editorial_daily/workday 干跑链路完整。发现的 5 个问题均为非阻断性缺陷（2 个 P2：工作日跳过状态被误报为成功、自由会议 heartbeat 缺失导致会话被误杀；3 个 P3：worker 无兜底、存稿失败诊断丢失、dry-run 副作用），建议在下一迭代修复，不阻塞合入。

```json
{
  "findings": [
    {
      "title": "Keep preflight-skipped workdays distinct instead of closing them as completed",
      "body": "In `_close_locked` (tools/workday.py:398-403), `produce_status == \"skipped\"` maps to `final_status = \"completed\"`. When a scheduled workday's produce chain is skipped by preflight (e.g. daily_enabled=false), `editorial_daily._finish_run` writes status='skipped' with error \"日更已暂停…\", but the subsequent `workday.close` relabels the run as 'completed' and returns ok=True. Reproduced by calling `workday.close(dry_run=True)` on a row with status='skipped'/phase='awaiting_close': it returns `{'ok': True, 'status': 'completed', 'published': 0}`. The panel and export_flow_html then show \"上次成功\" for a day that produced nothing, while `daily()` itself deliberately keeps 'skipped' as a distinct terminal state.",
      "confidence_score": 0.85,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\workday.py",
        "line_range": {"start": 392, "end": 403}
      }
    },
    {
      "title": "Refresh free-meeting heartbeat during cold-timer speech so quiet rooms are not auto-failed",
      "body": "In free mode the only writer of `meeting_sessions.heartbeat_at` is `_process_event` (tools/meeting_free_loop.py:108); `_process_cold` (lines 131-146) and `_speak` never touch it. The cold timer (default 30s) keeps agents talking, but if the boss sends no message for >60 minutes, `get_active_session` (novel_editorial/services/meeting_session.py:120-140) and `_fail_orphan_sessions` (web_api.py:1267-1281) mark the running session 'failed', after which `_process_event` silently drops every submitted event (status != 'running' early return). An actively chatting room is killed with no alert. Refresh the heartbeat on cold-timer/agent speech or base liveness on the loop thread instead of the boss-message heartbeat.",
      "confidence_score": 0.8,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\meeting_free_loop.py",
        "line_range": {"start": 131, "end": 146}
      }
    },
    {
      "title": "Guard the free-meeting worker so an LLM failure cannot silently kill the loop",
      "body": "`_run_worker` (tools/meeting_free_loop.py:86-102) has no try/except around `_process_event`/`_process_cold`. `_maybe_compress` -> `summarize_history` -> `agent_meeting.ask` -> `_chat_with_retry` raises RuntimeError after 3 retries; the exception propagates out of the daemon worker, killing it without any audit row, and the already-consumed event is lost. The session remains 'running' (no heartbeat) until the 60-minute stale recovery. Wrap per-event processing so failures are audited and the queue keeps draining, matching the module's stated \"failures are explicit\" contract.",
      "confidence_score": 0.75,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\meeting_free_loop.py",
        "line_range": {"start": 86, "end": 102}
      }
    },
    {
      "title": "Surface stock-publish failures in failed_nodes/errors instead of dropping them",
      "body": "In `daily()` (tools/editorial_daily.py:1819-1828), `publish_batch` returns `{target, published, failures, warnings}` with no `ok`/`error` keys, so `if not result.get(\"ok\") and result.get(\"error\")` is dead code and `_run_tool`'s `ok is False` check never fires: per-chapter stock-publish failures (HTTP errors etc.) never reach `ctx.failed_nodes`/`ctx.errors`/warnings, and flow_graph cannot highlight the 发布存稿 node. The run's overall status is still derived from `published` (partial/failed stays correct), but all failure detail is lost.",
      "confidence_score": 0.9,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\editorial_daily.py",
        "line_range": {"start": 1819, "end": 1828}
      }
    },
    {
      "title": "Make workday dry-run side-effect-free by skipping recover_stale_open",
      "body": "`workday.open(..., dry_run=True)` unconditionally calls `_recover_stale_open(conn)` (tools/workday.py:179), which UPDATEs `daily_runs` (marking stale rows failed, writing audit) and then acquires a lock file. This is the only DB mutation in the dry-run path and contradicts the codebase's dry-run convention (\"dry-run 不落任何库\"). A dry-run open can permanently mark a real stale workday row as failed.",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\workday.py",
        "line_range": {"start": 175, "end": 179}
      }
    }
  ],
  "overall_correctness": "patch is correct",
  "overall_explanation": "Baseline is green: compileall passes on all 27 slice files, 92 targeted slice tests pass, and editorial_daily/workday/export_flow_html dry-runs complete correctly. The 5 findings are non-blocking robustness/reporting issues (2 P2, 3 P3) that do not break existing code or tests and should be fixed in the next cycle.",
  "overall_confidence_score": 0.8
}
```
