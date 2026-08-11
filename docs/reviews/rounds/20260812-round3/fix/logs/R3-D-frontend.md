修完了mashitawa，六项全落，测试和构建都跑绿了desuwa。

[api.js](E:/code/novel-editorial/webapp/src/api.js:1) 现在是统一出口：`API_BASE` 导出给其他页面用；`getJSON` 网络失败抛「无法连接后端服务（网络错误）」，`postJSON` 捕获网络错误、非 2xx、JSON 解析失败后一律返回 `{ ok:false, error }` 结构，不再静默抛未处理 Promise。我把组内所有调用方都核对过，全都检查 `r.ok`，组外的 SettingsPage、DashboardPage、CommandPalette 也兼容，不会重复包裹desuwa。

[AgentsPage.jsx](E:/code/novel-editorial/webapp/src/components/AgentsPage.jsx:127) 心情读写 key 统一了：读取时先把 `selected.file` 去掉 `.md` 再匹配 `states.agent`，和后端 `agent_states` 实际存储的 `planner` 这类键一致，保存后立刻能回显mashitawa。[WorksPage.jsx](E:/code/novel-editorial/webapp/src/components/WorksPage.jsx:352) 手动绑定包了 try/catch/finally，失败时按钮恢复、toast 报错，不再卡「绑定中」。 [FlowPage.jsx](E:/code/novel-editorial/webapp/src/components/FlowPage.jsx:4) 删了重复的 `API_BASE` 死代码，改从 api.js 统一导入。

[App.jsx](E:/code/novel-editorial/webapp/src/App.jsx:139) 初始请求失败时不再永久骨架屏，改成「无法连接后端服务」面板加重试按钮，恢复后轮询照常接管。[desktop/package.json](E:/code/novel-editorial/desktop/package.json:38) 的 extraResources 加了 `scripts/**`，`install_daily_task.ps1` 会进包；计划任务的 DB 路径依赖现有 `_db_path()` 传播链（web_api 已把活动库设成 userData/demo.db），PS1 里 `Join-Path` 在打包布局下能正确解析到用户数据目录desuwa。

验证：webapp 里 `npx vitest run` 7 个文件 16 个测试全过，`npm run build` 通过（2.27s，只有 chunk 超 500KB 的既有警告），package.json JSON 校验通过。测试文件不在指派范围，建议补：心情保存后回显、绑定请求失败按钮恢复、App 离线错误态、postJSON 网络错误返回结构，各一条就行desuwa。

额外发现两个只报告不改的点：打包版计划任务靠 PATH 上的 `python`/`PYTHON_EXE` 注册，应用本体却用 `pythonw`，目标机 Python 不在 PATH 时定时任务仍会失败，这要动 install_daily_task.ps1 或 main.js，不在本轮清单里；另外审查里说的 main.js dialog 未导入那个 P1，我确认当前工作区顶部已经导入了，属于已解决状态。MEMORY.md 没动，本轮只改了指派文件mashitawa。
