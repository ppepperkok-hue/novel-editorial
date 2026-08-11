基线验证：webapp `npm test` 17/17 通过、`npm run build` 成功，desktop 与 webapp/src 的 4 个 JS 文件 `node --check` 语法通过；前端 api.js 全部端点与 novel_editorial/web_api.py 路由、control/knowledge_drafts/meetings/agent_actions 等入参契约逐项核对一致（含 desktop panelToken 与后端 _panel_token 的 ~/.n8n/.env 一致性）。审查范围 webapp/src + desktop 未发现 P0/P1 级阻塞缺陷，7 条发现均为 P2/P3：1 条长期可靠性（API 重启计数不复位）、其余为死代码、静默失败/假绿灯与 UX 文案问题。

Full review comments:

- [P2] API 自动重启计数永不重置，常驻托盘应用最终失去自愈能力 — E:\code\novel-editorial\desktop\main.js:101-106
  `desktop/main.js:105` 的 `apiRestartCount += 1` 在进程生命周期内只增不减，整个文件没有任何重置路径（API 成功响应或稳定运行后不复位）。对长期驻留托盘的桌面应用，后端累计异常退出 3 次（端口冲突、Python 崩溃等，代码自带重启机制即说明这些场景可预期）后，`desktop/main.js:101` 的 `apiRestartCount >= API_RESTART_MAX` 分支永久放弃自动重启，只发一条通知，用户必须手动重启应用才能恢复，且无法通过重开窗口触发 `ensureApi` 修复。建议在 `apiReady()` 探测成功或 API 连续运行一段时间后把计数清零。

- [P3] desktop 的 api-error IPC 消息无任何接收方，错误提示依赖系统通知 — E:\code\novel-editorial\desktop\main.js:88-100
  `desktop/main.js:89` 与 `desktop/main.js:99` 在 pythonw spawn 失败或后端异常退出时执行 `win.webContents.send("api-error", msg)`，但 `desktop/preload.js` 未暴露任何事件订阅接口，`webapp/src`（Shell.jsx/App.jsx 等）也没有 `api-error`/`onApiError` 监听（已 grep 确认）。消息发出即被丢弃，页面内无错误提示，仅剩 Windows 系统通知兜底；若系统通知被禁用，用户对后端故障完全无感知。要么在 preload 暴露 `onApiError` 并让前端展示，要么删除这两处 send。

- [P3] ExecutionsPage 的 snapshot prop 从未使用，SSE 实时快照被丢弃 — E:\code\novel-editorial\webapp\src\components\ExecutionsPage.jsx:29-29
  `webapp/src/components/ExecutionsPage.jsx:29` 解构了 `snapshot` 但组件体内再无任何引用（全文仅出现 1 次），而 `App.jsx` 以 `executions: () => <ExecutionsPage snapshot={liveSnapshot} />` 传入实时快照。结果执行记录页完全依赖自身 30 秒轮询（`getExecutions`），与其它页面基于 SSE 的实时状态（如首页 `liveExecs`）脱节，运行中状态最长滞后 30 秒；该 prop 与接线均为死代码，应删除或改为使用快照。

- [P3] 快捷键帮助文案声称 1–12，实际数字键只能直达 1–9 — E:\code\novel-editorial\webapp\src\App.jsx:101-102
  `webapp/src/components/Shell.jsx:172` 的帮助弹窗渲染 `1 – ${NAV.length}`（即 "1 – 12：切换页面"），但 `webapp/src/App.jsx:101-102` 用 `Number(e.key)` 解析单个按键，只能触发 1–9（NAV 第 10–12 项 settings/meetings/audit 无法通过数字键直达）。文案与实现不一致，用户按 0/10 无效或误触。应把帮助文案改为 1–9，或为第 10–12 页补双键处理。

- [P3] 章节正文加载失败被静默伪装成“正文未落库”，误导用户 — E:\code\novel-editorial\webapp\src\components\ChaptersPage.jsx:76-78
  `webapp/src/components/ChaptersPage.jsx:77-78` 的 `openReader` 在 `getChapterContent` 抛错（网络断开、后端 500 等，`api.js` 的 `getJSON` 会 throw）时无条件 `setReaderBody("")`，随后 UI 显示“本章正文未落库（历史章节）”。真实缺失与加载失败被混为一谈，用户会误判为正常状态而放弃排查，属于静默失败。建议 catch 分支区分错误并展示重试入口，只有后端明确返回空 content 时才显示“未落库”。

- [P3] fetchControl 轮询错误被吞，侧边栏调度器状态短暂假绿灯 — E:\code\novel-editorial\webapp\src\App.jsx:60-60
  `webapp/src/App.jsx:60` 的 `usePolling(fetchControl, 15000)` 未接收返回值，fetchControl 失败时 zustand 的 `control` 保留上一次成功值，`online = Boolean(control?.scheduler)`（App.jsx:109）继续点亮“调度器在线”绿点，后端实际已断连。该假绿灯最长持续到 DashboardPage 自身 30 秒轮询把 control 置 null，期间用户看到的是过期在线状态。建议复用 `error` 状态或在失败时把 control 置 null。

- [P3] 关键交互页面与 desktop 主进程无自动化测试覆盖 — E:\code\novel-editorial\webapp\src\components\SettingsPage.jsx:1-1
  webapp 现有 7 个测试文件只覆盖 App/Audit/Chapters/Dashboard/Editorial/Executions/Works；无测试覆盖 SettingsPage（save_settings+apply_schedule 保存流程）、MeetingLive/MeetingsPage（会议轮询与会话推进）、AgentsPage（提示词保存/校验）、agent-panels（知识库/行动项/活动日志）、CostPage、ReaderPage、FlowPage；desktop 的 main.js（spawn/重启/托盘/自动更新）、preload.js、release.js 零测试。本次基线只能证明现有 17 条用例通过，上述路径的回归风险（如本文 F1/F5 所涉逻辑）无任何护栏。
