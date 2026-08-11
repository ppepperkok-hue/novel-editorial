审查范围：novel_editorial/ 全部 33 个模块 + services/ 契约验证。基线：python -m compileall 全部通过；web_api GET/POST smoke 测试（含 token 保护、路由、错误分支）全部符合预期；tools/ 下 22 个依赖接口签名全部匹配。未发现 P0/P1 阻塞问题；2 个 P2 均为会议会话状态机的边界场景（等待输入超时 + 面板重启/双实例），不破坏现有测试与常规路径，建议下一轮修复。

Full review comments:

- [P2] 会议等待输入循环缺少 failed 状态退出条件，线程永久轮询 — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:579-587
  meeting_session.py:579-587 的内层等待循环只处理 status 为 cancelled / running 的退出，session 若在等待用户输入期间被外部标记为 failed（例如第二个 web_api 实例启动时 `_fail_orphan_sessions` 命中 `awaiting_input`，或手动改库），循环将永远 `time.sleep(2)` 轮询：会议永不完成、weekly_meetings 报告不落库、后台线程泄漏，且 `advance_session` 会因状态不是 awaiting_input 拒绝继续。已用脚本模拟确认该循环对 failed 状态无任何退出分支。建议在循环中把 failed/finished 也视为终止条件。

- [P2] _fail_orphan_sessions 误杀等待输入的会议，转录与报告丢失 — E:/code/novel-editorial/novel_editorial/web_api.py:1179-1181
  web_api.py:1181 的孤儿会话清理把 `awaiting_input` 一并标记为 failed，与 meeting_session.py:102-103 中“awaiting_input sessions are left alone: the thread is parked waiting for the user, which is a legitimate state”的契约直接矛盾。用户开会后等待输入超过 60 分钟（heartbeat 不再更新）再重启面板（更新代码/配置是常见操作），重启时该会话会被判为孤儿并 failed：用户无法继续（advance_session 返回“当前状态不是等待输入”），本轮会议的报告、post-meeting actions 全部丢失。建议清理时排除 awaiting_input（或至少在心跳语义上区分“等待用户”与“线程死亡”）。

- [P3] get_active_session 对 NULL heartbeat_at 抛 TypeError，导致会议端点 500 — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:113-113
  meeting_session.py:113 的 `session.get("heartbeat_at", "")` 在 heartbeat_at 为 NULL 时返回 None（键存在但值为 None，dict.get 默认值不生效），`None < cutoff` 在 Python 3 抛 TypeError。已用内存库复现：`get_active_session RAISED: TypeError '<' not supported between instances of 'NoneType' and 'str'`。任何通过外部工具插入、未填写 heartbeat_at 的 running 会话（如测试 test_meeting_session.py:317 所示的外部创建路径）都会让 `/api/meetings/active` 与 `/api/meetings/start` 返回 500，且该异常会向上传播到 create_session/start_session_async。建议改为 `(session.get("heartbeat_at") or "") < cutoff` 或先判空。

- [P3] _origin_allowed 放行无端口本地 origin，可绕过面板 token 写保护 — E:/code/novel-editorial/novel_editorial/web_api.py:56-61
  web_api.py:56-61 的允许列表包含不带端口的 `http://127.0.0.1` / `http://localhost`（即本机 80 端口）。由于 `_guard` 只对“无 Origin 的 POST”强制 Bearer token（web_api.py:336-340），本机 80 端口上任何其他本地服务页面都可以携带该 Origin 发起 POST，无 token 即可触发 control 的 run_now（会真实调用 LLM、产生费用）、knowledge 写入、refresh_hot_topics 等操作。属低概率但真实的跨源攻击面；建议从允许列表移除无端口项，或对这类 origin 也要求 token。

- [P3] load_meetings 解析 attendees 无异常保护，损坏数据导致 500 — E:/code/novel-editorial/novel_editorial/services/misc.py:116-116
  misc.py:116 对 `r["attendees"]` 直接 `json.loads(r["attendees"] or "[]")`，与同一函数里 report 字段的 try/except 处理不对称；一旦库中存在损坏的 attendees JSON（外部写入或历史数据），`/api/meetings` 整个端点会抛异常返回 500，前端会议列表不可用。建议与 report 解析保持一致的容错。
