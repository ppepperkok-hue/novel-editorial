审查完了。报告如下——先给结论，再上证据。

---

# 审查报告：tools/ 调度与编辑部协作切片

## 范围（Scope）

21 个目标文件全部通读：`editorial_daily.py`、`workday.py`、`editorial_steps.py`、`editorial_state.py`、`flow_graph.py`、`export_flow_html.py`、`daily_runs.py`、`auto_fill_actions.py`、`agent_context.py`、`agent_meeting.py`、`agent_tool_loop.py`、`mailroom.py`、`relations.py`、`promises.py`、`meeting_actions.py`、`meeting_kinds.py`、`meeting_materials.py`、`write_diaries.py`、`architect_weekly.py`、`apply_architect.py`、`app_settings.py`。

依赖接口只读不扫：`novel_editorial/db.py`、`config.py`、`llm_client.py`、`services/{activity,audit,agency}.py`、`tools/{preflight,publish_stock,check_stock,current_book,record_work,novel_knowledge,collect_reader_stats}.py`、`backup.py`。

## Baseline 结果

- `python -m compileall` 21 个文件：**通过**（COMPILEALL_OK）。
- 目标切片测试（fresh 库）：`test_relations / test_mailroom / test_editorial_state / test_flow_graph / test_export_flow_html / test_promises / test_meeting_actions / test_meeting_materials / test_auto_fill_actions / test_agent_tool_loop / test_editorial_daily(部分)` 共 66 个用例，**全部通过**。
- 复现验证均在临时库/副本上进行，未改动工作区数据。

测试全绿，但下面两个 P1 都在"测试覆盖不到的路径"上——一个是旧库升级，一个是 dry-run 真实副作用。测试库永远是全新 schema，所以抓不住它们。

## P0–P3 Findings

### [P1] 旧库 schema 与代码不兼容：默认 CLI 库上日更链路必失败

`tools/relations.py:56-60`（以及 `mailroom.py:163`、`editorial_daily.py:1066/854/571`）的 SQL 使用 `other` 列与 `resolution` 列，但 `novel_editorial/db.py:_migrate`（370-502 行）只做加列，**没有** `other_agent → other` 重命名、也没有 `agent_messages.resolution` 迁移。工作区自带的 `demo.db`（全部 CLI 的默认 `--db`）正是旧结构，实测：

```
relations.ensure(conn,'writer','eic',1)  → OperationalError: no such column: other
editorial_daily.daily(dry_run=True, db_path=demo.db)
  → status=failed, error="调度器异常: no such column: other"
mailroom.resolve(conn, id, 'done')       → {'ok': False, 'error': 'resolve failed: no such column: resolution'}
```

demo.db 的 `agent_relations` 列是 `other_agent`、`agent_messages` 没有 `resolution`（已用 PRAGMA 对比确认）。后果分三层：日更在 `_run_track` 的 `relations.apply_event` 处抛异常导致整次运行 failed；mailroom 的 resolve 静默失败（错误只进返回 dict）；`editorial_state.list_relations` 因 try/except 静默返回空，面板协作数据凭空消失。任何从旧版本升级的库都会踩中，作者需要补迁移或重建 demo.db。

### [P1] `--dry-run` 会真实写库：任务被标完成、关系被改、设置被清

`tools/editorial_daily.py:1301`（`_wrapup` 无条件调用 `_settle_claimed_tasks`），以及 1066/1089/1135/1038 行 `relations.apply_event`、523 行 `audit.log`、1589 行 `set_many({"pending_publish": "0"})` 都没有 `dry_run` 分支。fresh 库实测 `daily(dry_run=True)`：

```
agent_actions status: claimed → done      （真实 UPDATE）
agent_relations rows: 0 → 2               （真实 INSERT）
audit_logs rows:      0 → 1               （真实 INSERT）
```

而引入 outbox 的提交 6cc95fb 提交信息白纸黑字写着 *"Dry-run stays side-effect free"*——这是违背作者自己承诺的回归。用户跑一次 `--dry-run` 验证流水线，任务板上的 claimed 任务就被标成完成、writer–eic 信任/摩擦被改写、`pending_publish` 手动档被清零。dry-run 只应走占位文本，不该碰任何表。

### [P2] `_unwrap_text` 会剥离 `outbox`/`agency` 字段，S4 留言与 R3-1 动作静默丢失

`tools/agent_tool_loop.py:140-153`：`_unwrap_text` 对 `{"text": ..., "outbox": [...]}` 直接返回 `obj["text"]`，其余字段丢弃。复现：

```
{"text": "正文", "outbox": [...]}  →  _unwrap_text 后 = "正文"（outbox 消失）
```

`_handle_outbox`/`_handle_agency` 在 `editorial_daily.py:350-351` 处理的是 `agent_tool_loop.run()` 已 unwrap 过的文本，永远看不到 outbox。时间线坐实这是交互缺陷：`_unwrap_text` 引入于 bee1117（08-11 13:34），`_handle_outbox` 引入于 6cc95fb（08-11 20:12），后者加在已存在的 unwrap 之后。模型一旦按常见习惯输出 `{"text":..., "outbox":[...]}` 混合结构，agent 间的留言和自主动作就被静默吞掉。

### [P2] `auto_fill_actions --days N` 参数完全无效

`tools/auto_fill_actions.py:46-48`：`collect_evidence(conn, novel_id, days=1)` 的函数体只用 `_today()`，`days` 没参与任何查询；CLI `--days` 一路透传到 `run()` 再传给 `collect_evidence` 后石沉大海。用户传 `--days 7` 期望扩大回填窗口，实际永远只查当天——假参数，静默无效。

### [P3] `_mark_injected_read` 把 agent 自己发出的消息标成已读

`tools/editorial_daily.py:107-117`：`mailroom.list_messages` 对 agent 用 `(to_agent=? OR from_agent=?)` 匹配（`mailroom.py:90`），`_mark_injected_read` 把返回的全部 unread 消息（含 `from_agent=当前agent` 的）`mark_read`。A 通过 outbox 发给 B 的消息，在 A 下次被调用时就被标 read，B 的收件箱未读提示失效。低影响但违背"未读"状态机的语义。

### [P3] `round_speech` 中 `if tool_calls:` 分支是死代码

`tools/agent_meeting.py:431-486`：`ask()` 内部（209-253 行）已完整处理工具循环，返回的 `tool_calls` 恒为 `[]`（253 行），431 行的分支永不执行，且 479 行对 `ask` 的二次调用与内部逻辑重复。功能无碍，纯维护负担，建议删除。

### [P3] `weekly_payload` 对历史日记的 `json.loads` 无保护

`tools/write_diaries.py:118-120`：`json.loads(d["content"])` 直接执行，历史行 content 一旦非合法 JSON（旧版本或手工编辑），`write()` 抛异常中断整批周记。其余解析路径都有容错，这里漏了。

## 影响表

| # | 严重度 | 位置 | 影响 | 触发条件 | 复现 |
|---|--------|------|------|----------|------|
| 1 | P1 | relations.py:56-60 / mailroom.py:163 | 日更失败、消息解析静默失效、面板数据消失 | 使用旧 schema 库（含默认 demo.db） | 实测 OperationalError |
| 2 | P1 | editorial_daily.py:1301/1066/1589 | 任务误标完成、关系/信任被改、手动档被清 | 任何 `--dry-run` 运行 | fresh 库实测 claimed→done |
| 3 | P2 | agent_tool_loop.py:140-153 | outbox/agency 静默丢失 | 模型输出 text+outbox 混合结构 | 复现脚本确认 |
| 4 | P2 | auto_fill_actions.py:46-48 | `--days` 参数无效 | 传 `--days` 时 | 代码路径确认 |
| 5 | P3 | editorial_daily.py:107-117 | 收件人未读标记丢失 | outbox 消息 + 发件人再次调用 | 代码路径确认 |
| 6 | P3 | agent_meeting.py:431-486 | 无（死代码） | — | 代码路径确认 |
| 7 | P3 | write_diaries.py:118-120 | 周记整批中断 | 历史脏 content | 代码路径确认 |

## 结论

诚实的结论是：**这个切片不能算正确**。测试 66 个用例全绿是真，但两个 P1 都在测试的盲区里——全链路 `--dry-run` 会真实污染生产数据（违背提交信息里 "Dry-run stays side-effect free" 的明确承诺），旧库升级路径（默认 demo.db）直接让日更崩在 `no such column: other`。这两条都是作者知道后一定会修的级别。P2/P3 共五条，前两条（outbox 被 unwrap 吞掉、days 参数假死）也是实打实的功能缺陷，其余三条属于低风险卫生问题。

overall verdict: **patch is incorrect**（P1 阻断项存在）。这七个问题里，我最想让您先看的是第一个——它意味着升级用户第一天就会收到 failed 的日更，而且错误信息藏在 error 字段里，面板上只有一片红，desuwa。
