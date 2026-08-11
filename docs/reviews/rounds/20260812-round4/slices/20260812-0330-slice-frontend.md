审查范围：webapp/src（全部 JS/JSX）与 desktop（main.js/preload.js/release.js/package.json），后端仅按契约验证。基线：npm test 16/16 通过、npm run build 成功、desktop 三个 JS 文件 node --check 通过。结论：存在 1 个 P0——保存设置后计划任务注册在 PowerShell 5.1 下必然失败却被报告为成功，桌面版自动日更功能整体失效（静默）；另有 1 个 P1（安装到非 C 盘时 apply_schedule 500）、2 个 P2、4 个 P3。在修复 P0（ps1 编码 + 后端成功判定）前，桌面版“每日自动更新”核心链路不可用，因此判定为不正确。

Full review comments:

- [P0] 保存设置时 Windows 计划任务注册静默失败，自动日更永不触发 — E:\code\novel-editorial\webapp\src\components\SettingsPage.jsx:82-89
  webapp/src/components/SettingsPage.jsx:82-89 的保存流程调用 `apply_schedule` 后，只要 `sched.ok` 就提示“日更时间已改为每天 …”，但实测该路径实际注册失败：`scripts/install_daily_task.ps1` 是无 BOM 的 UTF-8 文件，Windows PowerShell 5.1 按 ANSI/GBK 解码后中文变成乱码（实测输出 `宸叉敞鍐岃…`），`Register-ScheduledTask` 抛 `ParameterBindingArgumentTransformationException`（Cannot convert value "杩愯銆?" to type CimInstance…className），脚本仍以退出码 0 结束；novel_editorial/services/control.py:303-311 仅按 `returncode==0` 判定成功，于是 API 返回 `{"ok": true, "deploy": {"ok": true}}`，前端弹出成功 toast，但 `Get-ScheduledTask NovelEditorialDaily` 确认任务从未创建。净效果：桌面应用“保存设置”后每日自动更新功能完全失效且无任何失败提示，属静默失败（fake green），需要给 .ps1 加 BOM（或改为 ASCII 文本）并在后端校验注册结果。

- [P1] 桌面版安装到非 C 盘时保存设置必然 500，自动日更失效 — E:\code\novel-editorial\desktop\main.js:51-54
  desktop/main.js:51-54 打包模式下把 DB 放在 `app.getPath("userData")/demo.db`（通常 C 盘），而 `ROOT` 是 `resources\novel-pipeline`（安装目录）。保存设置时 novel_editorial/services/control.py:290 执行 `os.path.relpath(_db_path(), ROOT)`，跨盘时抛 `ValueError: path is on mount 'C:', start on mount 'E:'`（已实测复现并记录在 alerts.log），`apply_schedule` 返回 500，SettingsPage.jsx:87-89 只显示“更新时间应用失败：internal error”，计划任务不注册。用户把安装目录选在 D/E 盘（安装器允许自定义目录）时该问题必然出现。

- [P2] Agent 保存失败时校验详情分支不可达，用户看不到失败原因 — E:\code\novel-editorial\webapp\src\components\AgentsPage.jsx:171-181
  webapp/src/components/AgentsPage.jsx:171-181：后端 novel_editorial/services/agents.py agent_save 在渲染或校验失败时总是返回 `ok:false`（并把文件回滚），前端 `if (!r.ok) { … return; }` 提前退出，因此 `r.validation` / `r.validation_output` 分支永远执行不到；用户只看到“保存失败：render/validate failed”，看不到 render 输出与校验输出，且“已保存，但工作流校验未通过”的 toast 文案具有误导性（此时文件实际已被回滚、并未保存）。建议失败路径也展示 `r.render`/`r.validation_output`。

- [P2] release.js 发布流程不先构建 webapp，会打包旧前端 — E:\code\novel-editorial\desktop\release.js:37-37
  desktop/release.js:37 只执行 `npm run dist`（electron-builder），而 desktop/package.json 的 extraResources 打包 `webapp/dist/**`。若发布前前端有改动但未执行 `npm run build`，安装包内嵌的是旧版前端；若 webapp/dist 不存在则产物残缺。发布脚本应在打包前先构建 webapp。

- [P3] 托盘通知不覆盖 partial 状态，部分成功静默无提示 — E:\code\novel-editorial\desktop\main.js:179-179
  desktop/main.js:179 的通知过滤列表 `["success","error","failed","crashed"]` 不含 `partial`（tools/daily_runs.py local_executions 会原样透传 `partial` 状态），日更“部分成功”时桌面不会弹通知，用户可能误以为完全成功或失败。建议加入 `partial`。

- [P3] 快捷键帮助文案“1 – 8”与实际 12 个导航项不符 — E:\code\novel-editorial\webapp\src\components\Shell.jsx:141-141
  webapp/src/components/Shell.jsx:141 HelpModal 中写死 `["1 – 8", "切换页面"]`，而 NAV 有 12 项且 App.jsx 实际支持 1–12 数字键切换，帮助内容与行为不一致，容易误导用户。

- [P3] vite dev 模式无代理，npm run dev 无法联调后端 API — E:\code\novel-editorial\webapp\vite.config.js:1-20
  webapp/vite.config.js 未配置 `server.proxy`，而 src/api.js:2-3 在有 host 时 `API_BASE=""`，`npm run dev`（5173 端口）下所有 `/api/*` 请求打到 vite dev server，返回 SPA fallback 的 HTML，`getJSON` 的 `r.json()` 解析失败，面板持续显示“无法连接后端服务”。开发模式需配置 proxy 指向 127.0.0.1:8000（或使用生产构建由后端直接服务 dist）。

- [P3] 配置 PANEL_TOKEN 后桌面托盘 POST 缺少 Authorization，功能静默失败 — E:\code\novel-editorial\desktop\main.js:122-141
  desktop/main.js:122-141 的 triggerWorkflow 用 Node fetch 从主进程发 POST /api/control，无 Origin 也无 `Authorization` 头；web_api.py:335-338 的 `_guard` 在无 Origin 且设置了 PANEL_TOKEN 时强制校验 Bearer。若用户按后端设计配置了 PANEL_TOKEN（.env），托盘“立即更新一章/周会”会 403，仅通知“启动失败”。默认未配置时不受影响。
