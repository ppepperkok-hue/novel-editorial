七项全部修完，验证也跑齐了。给你按项交代 desuwa。

1. **R7-C1-01** [desktop/package.json](E:/code/novel-editorial/desktop/package.json:38)：在 `tools/**` 后补了 `!tools/chrome-profile` 和 `!tools/chrome-profile/**` 两条排除。我用 electron-builder 真实的 FileMatcher 模拟了一遍，chrome-profile 零命中；又实跑了一次 `--dir` 打包到临时目录，产物里 `hasChromeProfile=False`，tools 目录确认没有它了mashitawa。

2. **R7-C1-02** [desktop/main.js](E:/code/novel-editorial/desktop/main.js:131)：`createWindow` 加了幂等护栏，`showWindow` 在启动未就绪时只置 `showRequested` 标志不建窗，等 `ensureApi` 完成后在主窗口创建处统一显窗聚焦（358-363 行）。二次启动落在启动窗口期内不会再开第二个窗，第一个窗口也不会泄漏desuwa。

3. **R7-C1-03** [desktop/main.js](E:/code/novel-editorial/desktop/main.js:74)：抽出 `spawnApiProcess`，监听 `exit`，运行期崩溃时先发通知再自动重启，间隔 3 秒、上限 3 次，超限后明确提示手动重启；`apiStopping` 保证退出时不会误触发重启，窗口真正关闭时也会先置标志再杀进程desuno。

4. **R7-C1-04** [desktop/main.js](E:/code/novel-editorial/desktop/main.js:233)：`triggerWorkflow` 的 catch 从只写 console 改成 `notifyIssue` 托盘通知，网络失败不再无声desuwa。

5. **R7-C1-05** [desktop/main.js](E:/code/novel-editorial/desktop/main.js:115)：`ensureApi` 改为等待 `spawn`/`error` 事件，pythonw 不存在时立即 reject 走错误对话框退出，不再白等 20 秒mashitawa。

6. **R7-C1-06** [desktop/main.js](E:/code/novel-editorial/desktop/main.js:267)：轮询请求加了 10 秒 AbortController 超时，轮询体加了 `pollingInFlight` 重入保护，上一轮挂起时本轮直接跳过，不会叠加请求desuwa。

7. **R7-C1-07** [scripts/install_daily_task.ps1](E:/code/novel-editorial/scripts/install_daily_task.ps1:25)：新增 `Resolve-PythonExe`，按 `PYTHONW_EXE`/`PYTHON_EXE`（校验绝对路径且存在）→ 打包布局自带解释器（`.venv\Scripts\pythonw.exe`、`python\pythonw.exe` 等）→ PATH 上 pythonw/python 的顺序解析，全找不到就显式报错并 exit 1，绝不在没有解释器时悄悄注册一个必失败的定时任务desuwa。

验证结果：`node --check` 通过，package.json JSON 解析通过，ps1 用 PowerShell 5.1 Parser 解析通过；DryRun 实测解析出 `.venv\Scripts\pythonw.exe` 绝对路径，把 `PYTHONW_EXE` 指向不存在的文件时正确报错退出码 1，剥掉 PATH 后也能命中打包布局候选。只改了这三个文件，没做 git add/commit，也没更新 MEMORY.md。

额外发现，只报告不动手：`desktop/release/win-unpacked` 里上一轮构建的 chrome-profile 还在（104MB 会话数据），发布前必须重新打包，本任务范围不允许我清理它；另外 `tools/archive`（约 4.3MB 开发归档）和 `tools/__pycache__` 仍会随 `tools/**` 进包，后续值得把过滤改成更细的白名单，这手我看不上但现在不碰desuwa。
