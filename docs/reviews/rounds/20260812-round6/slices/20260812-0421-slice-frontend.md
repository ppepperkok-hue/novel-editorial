审查范围 webapp/src 与 desktop（不含 node_modules/dist/lockfile）。基线：`npm run build` 通过（vite 5.4.21，984 模块，仅 >500kB chunk 警告）、`node --check main.js/preload.js` 通过、契约文件 `python -m py_compile` 通过、全部切片文件逐字节验证为合法 UTF-8（此前乱码仅为控制台显示问题）。e35d379 引入一处真实回归：watchExecutions 改为进程内 Set 后每次启动会对最近 30 条终态执行补发通知（P2），另有手动刷新错误状态失联（P3）与 .npmrc 硬编码路径（P3）；均不阻塞构建与既有测试，但非纯 nit，建议修复后合入。

Full review comments:

- [P2] 桌面端每次启动都会对最近 30 条终态执行补发系统通知 — E:\code\novel-editorial\desktop\main.js:206-218
  e35d379 把 `lastExecKey`（仅首条、且首轮轮询被 `lastExecKey &&` 抑制）改成进程内 `notifiedExecKeys` Set（desktop/main.js:20, 206-218）。Set 不落盘，每次启动都为空，而 `/api/executions` 返回 `daily_runs.local_executions(conn)`，默认上限 30 条（tools/daily_runs.py:170-171），其中终态（success/error/failed/crashed/partial）记录会在启动后第一次轮询（30 秒）时全部触发一次 `new Notification(...)`。复现：DB 里有 ≥1 条历史终态执行 → 每次重启桌面应用都会弹出一串（最多 30 条）"日更执行成功/失败"通知；旧实现只在状态发生跳变时通知一次。建议只对 `started_at` 晚于本次启动时间的执行发通知，或将已通知 key 持久化。

- [P3] 手动刷新不再更新 dashboardError，失败静默、恢复后错误横幅最多残留 5 秒 — E:\code\novel-editorial\webapp\src\App.jsx:59-70
  e35d379 把 App.jsx 的 `refresh` 从 `refreshDashboard()`（触发 usePolling 内部 tick，tick 会 setError/清 error）改为直接 `await fetchDashboard()` 并仅在 catch 里 `console.error`（webapp/src/App.jsx:59-70）。后果：后端离线时点"重试"，失败只进控制台，`dashboardError` 不更新；后端恢复后手动刷新成功，DashboardPage 的"后端连接失败"横幅（DashboardPage.jsx:230-232）仍显示旧错误，直到下一次 5 秒轮询成功才清除。建议在 refresh 成功后显式清空 usePolling 的 error（例如保留 `refreshDashboard` 并同时触发 tick），失败时也写入 error 状态。

- [P3] webapp/.npmrc 提交了本机绝对路径缓存目录 — E:\code\novel-editorial\webapp\.npmrc:1-1
  `webapp/.npmrc` 被 git 跟踪（`git ls-files` 确认），内容为 `cache=E:\code\.npm-cache`，是机器相关的硬编码绝对路径。在无 E: 盘的其他机器上克隆仓库后执行 `npm install`，npm 会尝试把该路径当缓存目录并失败，导致前端依赖安装不可用；该路径也泄露了本机目录结构。建议删除该行或改用相对/环境变量（如 `$env:LOCALAPPDATA` 或 npm 默认缓存），或将该文件加入 .gitignore。
