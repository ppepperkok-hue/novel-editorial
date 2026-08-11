验证基线通过：webapp `npm run build`（vite 5.4.21）成功，desktop 的 main.js/preload.js/release.js 均通过 `node --check`，前端所有 API 调用与后端路由/返回结构（/api/control、dashboard、executions、meetings、agents、ending、knowledge、audit 等）逐一核对一致。未发现 P0/P1 阻断性问题；4 个发现均为 P2/P3 级功能与健壮性缺陷（认领 Agent 归属错误、result 被清空、更新检查静默失败、重启计数不重置），不影响发布与核心写作/发布链路。

Full review comments:

- EditorialPage 认领下拉的 defaultValue 与 option 值不匹配，认领总是落到第一个 Agent — E:/code/novel-editorial/webapp/src/components/EditorialPage.jsx:78-97
  `webapp/src/components/EditorialPage.jsx` 的 TaskBoard 下拉（第 78-97 行）`defaultValue={a.assignee || a.agent || agents[0]?.name}`，而 option 的 value 是 `ag.name`（agents 来自 `novel_editorial/services/agents.py:67-77`，name 为 AGENT_DISPLAY 中文显示名，如「策划官」），但 `a.assignee`/`a.agent` 是系统内部键（如 `planner`/`writer`，见 `services/activity.py` 的 create_action 与会议生成逻辑）。内部键永远匹配不到任何 option，select 的 value 为空（jsdom 实测 `selectedIndex=-1, value=""`），于是 `sel?.value || agents[0]?.name` 总是回退到第一个 Agent（按文件名排序是「文字编辑」），用户不手动改下拉时认领一律记到第一个 Agent 头上；即使用户手动选择，`claimed_by` 也会写入中文显示名，与系统其余部分（activity 日志、agent_actions.agent、agent_tool_loop 按内部键过滤）不一致。现有 editorial.test.jsx 的认领测试只断言发起了 POST，未断言 agent 值，因此未覆盖此问题。

- ActionsPanel「直接完成/跳过」会清空行动项已有 result — E:/code/novel-editorial/webapp/src/components/agent-panels.jsx:300-310
  `webapp/src/components/agent-panels.jsx:300-310` 的 `saveStatus` 在非编辑态固定传 `result: ""`（第 303 行），而后端 `novel_editorial/services/activity.py:204-212` 的 `update_action` 无条件执行 `result=str(result or "")` 覆盖。场景：用户通过「编辑 / 完成」保存过 result（`saveTask` 用 status="" 保持 pending 并写入 result），再点「直接完成」或「跳过」，已填写的 result 会被清空且无法恢复。建议 status/result/task 改为仅更新传入字段。

- desktop 自动更新检查失败被静默吞掉，无任何日志或提示 — E:/code/novel-editorial/desktop/main.js:332-332
  `desktop/main.js:332` 的 `autoUpdater.checkForUpdatesAndNotify().catch(() => {})` 完全吞掉错误：当更新通道不可达、GitHub Release 网络失败或 `electron-updater` 初始化失败时，用户既看不到通知也没有日志，配合 `autoDownload=true`（第 323 行）会出现「以为开着自动更新、实际从未检查」的静默失败。建议至少 `console.error` 并考虑通过 `update-error` 事件提示用户。

- desktop API 重启计数成功后不重置，三次崩溃后本会话内永久放弃重启 — E:/code/novel-editorial/desktop/main.js:101-110
  `desktop/main.js:101-110` 的 `apiRestartCount` 只增不减，`spawnApiProcess` 成功后也没有复位（`ensureApi` 轮询到 `apiReady` 即返回，未重置计数）。结果是：应用长时间运行时只要累计发生过 3 次后端退出（例如早期启动阶段端口被临时占用、内存抖动），后续即使只是偶发崩溃也不再自动重启，后端服务会一直保持死亡直到用户手动重启整个应用。建议在 `ensureApi` 成功或 `apiReady` 为真时把 `apiRestartCount` 归零。
