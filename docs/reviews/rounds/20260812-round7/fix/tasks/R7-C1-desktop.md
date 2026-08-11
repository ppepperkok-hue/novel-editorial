# 修复任务包 · R7-C1 桌面端

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（新发现 + 遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round7/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `desktop/main.js`
- `desktop/package.json`
- `scripts/install_daily_task.ps1`

## 修复项

### R7-C1-01（P1，新）desktop/package.json:31-37
现状：安装包打包 tools/chrome-profile，泄漏浏览器会话数据。
期望：打包排除 tools/chrome-profile（extraResources/文件过滤），并确认本机该目录不随包分发。

### R7-C1-02（P2，新）main.js:269-285
现状：启动窗口期内二次启动会创建第二个窗口且第一个窗口泄漏。
期望：单实例锁（requestSingleInstanceLock 或等窗口就绪标志），二次启动聚焦已有窗口。

### R7-C1-03（P3，新）main.js:71-75
现状：后端 API 进程运行期崩溃后桌面端无感知、不自动恢复。
期望：监听子进程 exit/close，崩溃时提示并自动重启（带次数上限），不静默。

### R7-C1-04（L-014）main.js
现状：triggerWorkflow catch 只写 console，网络失败托盘无提示。
期望：失败时托盘/通知提示。

### R7-C1-05（L-027）main.js
现状：pythonw spawn 失败白等 20 秒才报错退出。
期望：监听 spawn/error/exit 事件提前失败，不白等。

### R7-C1-06（L-031）main.js
现状：30 秒轮询无超时/重入保护，请求挂起时叠加请求。
期望：轮询加 in-flight 保护（上一轮未完成则跳过本轮）。

### R7-C1-07（L-012）install_daily_task.ps1
现状：打包版计划任务依赖 PATH 上的 python/pythonw，目标机无 PATH 时定时失败。
期望：使用应用自带的 python 可执行文件绝对路径（打包布局下解析），或注册时显式校验并报错。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`node --check desktop/main.js`；package.json JSON 校验；ps1 用 PowerShell 5.1 解析校验（不实跑注册）。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
