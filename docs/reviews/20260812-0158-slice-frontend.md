基线验证：desktop 三个 JS 通过 node --check；novel_editorial 接口文件与 tools/daily_runs、flow_graph、mailroom 通过 python -m compileall；webapp npm run build 成功（仅 charts chunk 527KB 超 500KB 警告）；按指示未跑完整测试套件。webapp/src 与后端契约逐一核对基本一致，但 desktop 打包链路存在 P1 级数据库分叉：打包版 UI（userData/demo.db）与所有后台运行（config.DB_PATH=resources/novel-pipeline/demo.db）读写不同的库，且 demo.db 未打进包导致种子逻辑失效，发布版的核心“运行-查看”闭环是断的，故整体判定为不正确。

Full review comments:

- [P1] 打包版桌面端 UI 与后台运行使用两个不同的 SQLite 数据库 — E:\code\novel-editorial\desktop\main.js:51-61
  desktop/main.js:51-61 在打包模式下把 API 以 `--db <userData>/demo.db` 启动（并试图把 ROOT/demo.db 复制过去做种子），但 web_api.py 从不把 `--db` 覆盖到 `config.DB_PATH`（novel_editorial/config.py:28 固定为 `ROOT/demo.db`），而 control.py 的所有运行路径（run_now 日更/周会、close_workday、resume_workday、计划任务，见 novel_editorial/services/control.py:111,119,142,155,178,214-219）都写 `config.DB_PATH`。叠加 desktop/package.json:33-41 的 extraResources filter（只含 novel_editorial/**、tools/**、prompts/**、webapp/dist/**、web/**、README.md）不包含根目录 demo.db，导致打包后 (a) main.js:55-57 的种子复制永远不触发，userData/demo.db 首次启动是空库；(b) 托盘/面板触发的运行写入 resources/novel-pipeline/demo.db（该文件不存在时由 db.connect 新建；装在 Program Files 下通常只读，运行会静默失败），UI 读取的 userData 库永远看不到这些执行。开发模式仅因两条路径恰好重合（都是仓库根 demo.db）而正常。

- [P2] API 启动失败时桌面端无任何可见错误提示，直接静默退出 — E:\code\novel-editorial\desktop\main.js:217-223
  desktop/main.js:63-68 里 `apiProc.on("error")` 向 `win.webContents.send("api-error")` 发消息，但 spawn 发生在 createWindow()（main.js:224）之前，此时 win 为 null，消息必然被丢弃；且 preload.js 也没有任何监听。ensureApi 超时抛错后 main.js:217-223 仅 console.error 后 app.quit()——打包版 spawn 用 `stdio:"ignore"`，用户双击 exe 后既无窗口也无托盘，在 pythonw 不在 PATH 或 8000 端口被占（main.js:15 硬编码）时表现为“双击没反应”，没有任何对话框或日志路径提示。

- [P3] release.js 对同一版本重复执行必然中断，与注释宣称的幂等不符 — E:\code\novel-editorial\desktop\release.js:45-46
  desktop/release.js:45-46 直接 `git tag v${version}` + `git push origin v${version}`，execSync 遇到已存在的 tag 会抛错终止脚本；第 4 步的 `gh release view` 探测只覆盖“有 release”的情形，若上次运行在 tag 已推、release 未创建时中断，重跑会卡死在 tag 步骤。step 5 的 `--clobber` 注释宣称“re-runs are idempotent”，但 tag/push 两步使其不成立，版本回滚重发或失败重试都需要手动删 tag。

- [P3] 命令面板缺少 flow 与 editorial 两个页面入口 — E:\code\novel-editorial\webapp\src\components\CommandPalette.jsx:4-15
  webapp/src/components/CommandPalette.jsx:4-15 的 PAGE_CMDS 只列了 10 个页面，而 Shell.jsx:3-16 的 NAV 有 12 项（flow 链路、editorial 编辑部）。Ctrl+K 面板里无法搜索/跳转到这两个页面，与帮助里“切换页面”的承诺不一致。

- [P3] WorksPage 对 tags 直接 JSON.parse 无防护，非 JSON 会炸掉整页 — E:\code\novel-editorial\webapp\src\components\WorksPage.jsx:259-260
  webapp/src/components/WorksPage.jsx:259 执行 `JSON.parse(nextBook.tags || "[]")` 没有 try/catch。后端 ending_status（novel_editorial/services/ending.py:10-22）返回的是 novels.tags 的原始字符串，而 load_novels（services/dashboard.py:43-47）对同样的列做了 try/except 兜底——契约不一致。一旦 tags 列出现非 JSON 内容（如逗号分隔字符串），WorksPage 渲染抛 SyntaxError，被 ErrorBoundary 捕获后整页变成“页面渲染出错”，用户无法访问作品库。

- [P3] ui.jsx 的 fmtMoney 是无引用死代码 — E:\code\novel-editorial\webapp\src\components\ui.jsx:25-29
  webapp/src/components/ui.jsx:25-29 导出的 `fmtMoney` 在整个 webapp/src 中没有任何调用点（rg 仅命中定义处），属于死代码，可删除以免误导后续维护者以为成本展示使用了该格式化逻辑。

- [P3] desktop 目录完全没有自动化测试 — E:\code\novel-editorial\desktop\package.json:6-11
  desktop 的 main.js/preload.js/release.js（package.json:6-11 的 scripts 只有 start/dist/release，没有 test）零测试覆盖，托盘触发、执行通知去重（watchExecutions 的 lastExecKey 逻辑）、单实例锁、数据库种子复制、自动更新等逻辑全靠手工验证；本次切片验证只能做到 node --check 语法通过。建议至少为 main.js 的纯函数（apiReady、通知 key 计算）补最小单测。
