审查范围 webapp/src 与 desktop（排除 node_modules/dist/release/package-lock.json），基线：webapp build 成功、16 个前端测试全过、desktop 三个 JS 通过 node --check。存在 1 个 P1（main.js 使用未导入的 dialog，启动失败路径必然 ReferenceError 崩溃）与 3 个 P2（心情读写 agent key 不匹配、绑定按钮失败卡死、打包版计划任务 DB 分叉），均需修复后才能视为正确。

Full review comments:

- [P1] dialog.showErrorBox 使用了未导入的 dialog，启动失败路径必然抛 ReferenceError — E:\code\novel-editorial\desktop\main.js:221-221
  desktop/main.js:221 在 ensureApi() 失败时调用 dialog.showErrorBox，但第 1 行 require("electron") 只解构了 app/BrowserWindow/ipcMain/Menu/Notification/Tray/nativeImage，没有 dialog。复现条件：打包版或开发版在 pythonw 不在 PATH、端口 8000 被占用时启动——catch 块（main.js:217-223）执行到 dialog.showErrorBox 即抛 ReferenceError: dialog is not defined，错误对话框永远不会弹出，主进程未捕获异常直接退出。这恰好是代码想覆盖的"双击没反应"场景，错误处理路径自身是坏的。修复：在 require 中加入 dialog。

- [P2] AgentsPage 心情面板读写使用不同 agent key，保存后永远无法回显 — E:\code\novel-editorial\webapp\src\components\AgentsPage.jsx:127-137
  webapp/src/components/AgentsPage.jsx:127 用 `states.find((s) => s.agent === selected?.file)` 读取心情（selected.file 形如 "planner.md"），而 :137 写入时传 `selected.file.replace(/\.md$/, "")`（"planner"）。后端契约确认 agent_states.agent 列存的是无 .md 的名字：tools/write_diaries.py:24-34 的 AGENTS 列表与 novel_editorial/services/misc.py:250 的 update_state 都写入无后缀名（demo.db 中 agent_diaries/agent_activity 均为 "editor" 这类值）。因此 moodOf 永远找不到记录，currentMood 恒为默认值：点"保存心情"提示"心情已更新"，但面板不变化、重新进入页面也读不回，用户会反复 DELETE+INSERT 同一行，功能形同虚设。修复：读取端也去掉 .md 后缀（或写入端保留 .md，二选一）。

- [P2] WorksPage 手动绑定书请求失败时按钮永久卡在“绑定中” — E:\code\novel-editorial\webapp\src\components\WorksPage.jsx:352-357
  webapp/src/components/WorksPage.jsx:352-357 的 onClick 里 `setBinding(nextBook.id)` 后 `await bindBook(...)`，只有成功路径才执行 `setBinding(null)`，没有 try/catch/finally。当后端离线或请求抛异常（api.js:10-16 postJSON 网络错误直接 reject）时，setBinding(null) 永不执行，按钮永久 disabled 并显示"绑定中…"，用户无法重试，且产生 unhandled promise rejection。其余异步按钮（confirmNextBook 等）也有同类问题，但只有此处有 busy 状态卡死。

- [P2] 桌面打包版保存每日时间后，计划任务指向资源目录种子库且脚本未打包 — E:\code\novel-editorial\desktop\package.json:31-41
  desktop/package.json:31-41 的 extraResources filter 不包含 scripts/**，install_daily_task.ps1 不会进包；而 novel_editorial/services/control.py:290 的 apply_schedule 仍用 `os.path.relpath(config.DB_PATH, ROOT)`（打包模式下即 resources/novel-pipeline/demo.db 种子库）注册计划任务，与运行库 userData/demo.db（desktop/main.js:53 spawn --db）分叉——round-2 的 active-db 传播修复覆盖了 run_now/close/resume，但漏掉了 apply_schedule。复现条件：打包版在"系统设置"修改"每日更新时间"并保存：save 成功但随后的 apply_schedule 返回 ok:false（脚本不存在），即便脚本存在，定时任务也会操作 Program Files 下的只读种子库，用户数据不更新。

- [P3] 多处按钮直接 await postJSON 无 catch，后端离线时静默失败且无提示 — E:\code\novel-editorial\webapp\src\api.js:10-16
  webapp/src/api.js:10-16 的 postJSON 不检查 HTTP 状态、网络错误直接抛异常，而大量调用点只有 try/finally 或完全无保护：DashboardPage.jsx:72-91（action/openWorkday/closeWorkday/resumeWorkday/collectHot）、MeetingLive.jsx:138-180（start/nextRound/finishMeeting/doCancel）、SettingsPage.jsx action/runNow/save、AgentsPage.jsx:136-137（saveMood/saveDiary）、agent-panels.jsx（open/save/runKeeper/act/distill/create/saveStatus/saveTask）、WorksPage.jsx:300（confirmNextBook）。复现条件：后端重启或 8000 端口不可达时点击这些按钮，操作静默失败（无 toast），浏览器控制台出现 unhandled rejection，用户误以为已触发。建议统一在 postJSON 层把网络错误转成 {ok:false,error} 或为调用点补 catch。

- [P3] 后端离线时 App 永久显示骨架屏，连接错误提示不可见 — E:\code\novel-editorial\webapp\src\App.jsx:139-141
  webapp/src/App.jsx:139 `if (!data) return <skeleton>`：/api/dashboard 拉取失败时 data 保持 null，页面只渲染 SidebarSkeleton，而 error（dashboardError）只在 :208 的 Topbar 中展示，该分支根本不渲染 Topbar。复现条件：后端未启动直接打开前端，用户看到无限"加载中"骨架屏，没有任何"连接失败"提示，无法区分加载中与故障。建议在 data 为 null 且 dashboardError 非空时渲染错误提示。

- [P3] FlowPage 重复定义 API_BASE，属死代码 — E:\code\novel-editorial\webapp\src\components\FlowPage.jsx:6-8
  webapp/src/components/FlowPage.jsx:6-8 重新声明了 `const API_BASE = location.protocol === "file:" ... ? "http://localhost:8000" : ""`，与 webapp/src/api.js:1-3 中的定义完全重复，仅用于 :161 的 export flow 链接。该值在 webapp 中恒为 ""（同源），重复定义易误导维护者（以为存在独立 base 配置），建议改为从 api.js 导出或直接使用相对路径。
