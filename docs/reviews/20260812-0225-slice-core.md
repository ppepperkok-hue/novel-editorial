语法与 121 个定向测试全部通过，但存在一个已复现的 P1 阻断性问题：不可信的 LLM agency 输入（非数字 action_id）会让 agency.apply 抛 ValueError，中断整批动作并导致日更链路失败；另有 2 个 P2 问题（agent_save 假绿灯、apply_schedule 硬编码 demo.db）需在下一周期修复。

Full review comments:

- [P1] agency._dispatch 对畸形 action_id 无类型防护，ValueError 中断整批动作并击穿日更链路 — E:\code\novel-editorial\novel_editorial\services\agency.py:60-98
  LLM 输出的 agency 数组是不可信自由文本，但 `_dispatch` 直接 `int(item.get("action_id") or 0)`（novel_editorial/services/agency.py:60），`apply` 的逐项循环（agency.py:98）没有 try/except。已复现：`agency.apply(conn, 'writer', 0, [{'action': 'claim_task', 'action_id': 'abc'}])` 抛 `ValueError: invalid literal for int() with base 10: 'abc'`，且同一数组中的后续合法项全部不执行、无审计记录。调用方 `tools/editorial_daily.py:170`（`_handle_agency`）无异常保护，一次畸形项会让整次日更运行失败；`meeting_session._handle_meeting_actions` 虽有兜底但也丢失其余合法动作。这与模块 docstring 声明的「白名单外一律拒绝并审计」设计意图相悖。建议在 `_dispatch`/`apply` 内做类型校验，畸形项按 rejected 处理并审计。

- [P2] agent_save 在渲染/校验失败时仍返回 ok=True，造成假绿灯 — E:\code\novel-editorial\novel_editorial\services\agents.py:139-144
  `agent_save` 中 `rendered.returncode` 从未检查，`validated.returncode` 只被放入 `validation` 字段（novel_editorial/services/agents.py:119-144），但结果始终是 `"ok": True`。当 `render_workflow.py` 渲染失败或 `node validate_workflow_deep.mjs` 校验失败时，代理 .md 文件已被改写而工作流未同步，前端看到「保存成功」且 audit 记录正常，实际配置已处于不一致状态。建议 render 失败或 validation 失败时返回 `ok: False` 并携带 error。

- [P2] apply_schedule 硬编码 demo.db，与 --db 参数及手动触发路径不一致 — E:\code\novel-editorial\novel_editorial\services\control.py:289-290
  `apply_schedule` 注册 Windows 计划任务时使用 `os.path.relpath(config.DB_PATH, ROOT)`（novel_editorial/services/control.py:289-290），固定指向 `demo.db`；而同文件的手动触发 `_background_daily`/`_background_workday` 均使用 `_db_path()`（即 web_api main 传入的 `--db`）。以 `--db custom.db` 启动面板时，手动运行写 custom.db，而计划任务每天跑 demo.db，形成双库数据分裂。应改用 `_db_path()`。

- [P3] monitor.run_checks 部分凭据场景不加载 .env 导致误报 Cookie/CSRF 缺失 — E:\code\novel-editorial\novel_editorial\monitor.py:36-42
  `run_checks` 仅在 FANQIE_COOKIE 与 TOMATO_COOKIE 都缺失时才合并 ~/.n8n/.env（novel_editorial/monitor.py:36-42）。若调用环境变量里已有 FANQIE_COOKIE 而 CSRF token 只在 .env 中（或反之），.env 不会被加载，随后 `not (env.get("FANQIE_CSRF_TOKEN") ...)` 判定为真，误报「番茄 Cookie/CSRF 缺失」告警。建议先合并 .env 再按 cookie/CSRF 配对判断。

- [P3] Scheduler.tick 未注入时钟时 date 字段为字符串 "None" — E:\code\novel-editorial\novel_editorial\scheduler.py:46-46
  `report = {... "date": str(self.now)}`（novel_editorial/scheduler.py:46），而 `self.now` 默认为 None，`str(None)` 输出 "None" 写入返回报告。该模块已标记 DEPRECATED，但 `monitor` 仍依赖其 `backlog_level`/`SAFE_BACKLOG`；建议默认 `datetime.now()` 或省略该字段。

- [P3] seed_demo.seed 在 published+reviewed 超过 chapters 时产生负数 draft 导致状态错位 — E:\code\novel-editorial\novel_editorial\seed_demo.py:21-26
  `draft = chapters - published - reviewed`（novel_editorial/seed_demo.py:21）可为负，此时 `statuses` 列表长度不等于 chapters，`enumerate` 截断后章节状态与 seq 错位（例如 chapters=2, published=2, reviewed=2 时只生成 2 章但前 2 个状态都是 published）。默认 CLI 参数不会触发，但作为公开函数建议校验 `published + reviewed <= chapters`。

- [P3] update_draft_status 对 reject/deprecate 也写入 accepted_at — E:\code\novel-editorial\novel_editorial\services\knowledge.py:224-228
  `UPDATE knowledge_drafts SET status=?, accepted_at=datetime('now','localtime')`（novel_editorial/services/knowledge.py:224）在拒绝或废弃草稿时同样填充 `accepted_at`，字段语义被污染；web_api 的 reject/deprecate 分支（web_api.py:918）会走该路径。应仅在 status='accepted' 时写 accepted_at。

- [P3] web_api do_POST 对垃圾 Content-Length 头抛 500 而非 400 — E:\code\novel-editorial\novel_editorial\web_api.py:645-647
  `length = int(self.headers.get("Content-Length") or 0)`（novel_editorial/web_api.py:645）没有 try 保护；`_guard` 中的同款解析有 try（返回 403 前的长度检查），但 do_POST 第二次解析会因非数字头抛 ValueError，落入通用 500 分支。畸形请求应返回 400。

- [P3] /api/agent_actions/create 的 session_id/meeting_id 未做整数清洗，非数字 payload 返回 500 — E:\code\novel-editorial\novel_editorial\web_api.py:731-739
  web_api.py:736-737 直接把 `payload.get("session_id")`/`payload.get("meeting_id")` 传给 `activity.create_action`，而 create_action 内部执行 `int(session_id or 0)`；前端或脚本传入非数字字符串时抛 ValueError → 500。同端点其他字段（novel_id）也有此风险，应统一用 `_parse_int`。

- [P3] load_hot_topics 对损坏的 hot_topics.json 无兜底，拖垮 /api/dashboard — E:\code\novel-editorial\novel_editorial\services\misc.py:36-42
  `payload = json.loads(config.HOT_TOPICS_JSON.read_text(encoding="utf-8"))`（novel_editorial/services/misc.py:39）无异常处理；`build_payload` 在 /api/dashboard 中调用它，文件一旦被手工编辑或写入中断（非原子写场景）损坏，整个仪表盘接口 500。建议像 load_reader_stats 一样返回 `{"present": False}` 兜底。

- [P3] agents._extract_node_system 为无调用方的死代码 — E:\code\novel-editorial\novel_editorial\services\agents.py:39-45
  `_extract_node_system`（novel_editorial/services/agents.py:39-45）在整个仓库无任何引用（已用 rg 确认），其手工字符串解析逻辑也与现役 `agents_list` 的 `node["parameters"]["jsonBody"]` 检查方式无关。建议删除以免误导后续维护者。
