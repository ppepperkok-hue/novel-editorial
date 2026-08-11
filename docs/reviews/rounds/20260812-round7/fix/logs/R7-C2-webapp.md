五个修复项都落地了mashitawa。验证也跑完了：`npx vitest run` 七个测试文件十六条用例全绿，`npm run build` 构建成功，只剩 charts 那个 527kB 的旧体积警告，跟本次改动无关desuwa。

[App.jsx](E:/code/novel-editorial/webapp/src/App.jsx:59) 一次改了两项。问号快捷键（R7-C2-01）把 `?` 分支挪到了 input/textarea/select 与修饰键豁免判断之后（第 93-99 行），现在输入框里敲问号只正常输入，不再弹帮助desuwa。轮询错误（R7-C2-04）删掉了本地 `dashboardError` 和 `trackedFetchDashboard`，直接用 usePolling 返回的 error（第 59-71 行）；手动刷新失败或需要清掉旧错误时触发一次轮询 tick 同步状态，成功且无旧错误时不会多发请求desuwa。

[ChaptersPage.jsx](E:/code/novel-editorial/webapp/src/components/ChaptersPage.jsx:38) 的 AI 味检测（R7-C2-02）加了独立 `tasteError` 状态，失败不再写占位结果，按钮立刻恢复可点，错误显示在阅读器里（第 231-235 行），重开阅读器也会清空desuwa。

[WorksPage.jsx](E:/code/novel-editorial/webapp/src/components/WorksPage.jsx:173) 把结束状态刷新收敛成 `loadEnding()`，统一带 catch 和 toast，四个调用点（第 308、331、366、524 行）全部替换，不再有未处理的 Promise 拒绝desuwa。

[SettingsPage.jsx](E:/code/novel-editorial/webapp/src/components/SettingsPage.jsx:52) 的 `action()`（52-58 行）和 `save()`（63-100 行）都补了兜底 catch，任何异常都会以 toast 显示，不再静默desuwa。

测试建议列在这里，测试文件不在指派范围所以没改：app.test 补「input 内按 ? 不弹帮助」；chapters.test 补「AI 味失败后按钮可重试且显示错误」；works.test 补「ending status 失败出 toast」desuwa。

额外发现只报告不改：SettingsPage 的 `runNow()`（98-113 行）和 `desktopApi.setAutoLaunch` 的链式调用同样没有 catch；App.jsx 里 `fetchControl` 的轮询错误也仍无人消费，后端断连时 control 会静默变 null；WorksPage 首次加载结束状态的 catch 还是空的（176 行），属于同类静默失败。另有一处取舍要说明：手动刷新在失败或有旧错误时会多发一次 dashboard 请求，这是不动 hooks.js 的前提下立刻同步错误状态的代价，很小，先这么定desuwa。

MEMORY.md 没动，工作区只碰了指派的四个文件，git 也没有任何提交操作mashitawa。
