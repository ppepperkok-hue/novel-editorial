五个修复都落地并验证过了mashitawa。我按项给你捋一遍desuwa。

R5-C-01，release.js 第 39~48 行和第 81 行：不再把 exe 复制改名，改成直接读 latest.yml 里的 `path` 字段，上传它指向的那个文件和对应的 .blockmap。现有 latest.yml 记录的是 `novel-pipeline-desktop-setup-1.0.0.exe`，release 目录里这个文件也实际存在，所以 electron-updater 下载路径和上传产物现在严格一致desuwa。

R5-C-02，main.js 第 50~64 行：新增 `userDbPath()`，运行库固定放 `app.getPath("userData")/demo.db`，只有该文件不存在时才把打包种子 demo.db 复制过去。NSIS 升级会覆盖 resources 里的种子，但不会再碰用户数据目录里的库mashitawa。第 65 行 ensureApi 改用这个路径。

R5-C-03，main.js 第 257~258 行：ensureApi 失败时，错误框显示完后设置退出标志并 `app.quit()`，不留无窗口无托盘的幽灵进程desuwa。

R5-C-04，main.js 第 20 行和第 200~222 行：`lastExecKey` 换成 `notifiedExecKeys` 集合，轮询遍历 `/api/executions` 返回的全部记录（上限 30 条），每条终态记录只通知一次。同一个 30 秒窗口内完成多条执行也不会漏报了teyo。

R5-C-05，App.jsx 第 60~71 行：refresh 直接 await store 的 `fetchDashboard()`，`setRefreshing(false)` 挪进 finally。之前的 usePolling refresh 是同步的，等不到 fetch；现在按钮的禁用态和 spinner 在整个请求期间都真实生效，重复点击不会并发desuwa。

验证方面：`node --check` 对两个 desktop 文件通过；webapp 里 `npx vitest run` 是 7 个文件 16 个测试全过；`npm run build` 成功。git diff 确认只动了这三个文件，其他 agent 的改动我碰都没碰。

额外的发现，只报告不动手desuwa。最重要的一条：control.py 第 290 行对 DB 路径做 `os.path.relpath(_db_path(), ROOT)`，这正是当初把库挪进 resources 的原因；现在库回到 userData，跨盘符时（比如库在 C:、装在 E:）保存每日定时任务会抛 ValueError，需要后续在 control.py 里改用绝对路径。其次，main.js 里 pythonw spawn 失败时错误事件只发给尚未创建的窗口，而且会白等 20 秒才报错退出，建议以后监听子进程 close/exit 并提前失败。构建还有 charts chunk 超过 500KB 的警告，跟本轮无关，先记着desuwa。
