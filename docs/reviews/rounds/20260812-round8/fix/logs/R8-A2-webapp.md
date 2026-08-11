两处都弄好了mashitawa。

R8-A2-01 在 [ExecutionsPage.jsx](E:/code/novel-editorial/webapp/src/components/ExecutionsPage.jsx:32) 加了 `syncError` 状态，第62~66行从 `/api/daily_runs` 响应顶层接住 `sync_error`，第144~148行在「日更运行留痕」面板头部渲染红色错误横幅「每日运行同步失败：…」。同步失败立刻可见，下次同步成功字段为空，横幅自动消失desuwa。

R8-A2-02 在 [dashboard.test.jsx](E:/code/novel-editorial/webapp/src/__tests__/dashboard.test.jsx:38) 补了页面渲染冒烟测试：mock 掉 control 和 meetings 两个 fetch，断言 DashboardPage 渲染不抛错、关键区块（流程状态与补更、月度预算、健康检查、热点选题）都在，并等 fetch 落地后确认「● 已开启」出现，避免异步更新残留desuwa。

验证：webapp 目录下 `npx vitest run` 全过，7 个文件 17 个测试全绿；`npm run build` 成功，产物正常。剩下的只有既有的 charts 分包超 500kB 和 esbuild 弃用警告，不是这次引入的mashitawa。

额外问题只报不改：ExecutionsPage 第95行的 `fmt` 函数没人调用，是死代码；第229行空状态用了 `colSpan={7}`，表头实际只有6列，会多空一列desuwa。另外 `toggleRun` 拉详情失败时只是把 `runDetail` 置空，用户点开毫无反馈，建议以后加个轻提示teyo。MEMORY.md 没动mashitawa。
