审查范围：webapp/src（全部页面/组件/API 封装/测试）与 desktop（main.js、preload.js、release.js、package.json）。基线：webapp `npm run build` 通过（仅 react 空 chunk 警告）、`npm test` 45/45 通过、desktop 三个 JS `node --check` 通过。逐一核对了前端调用与后端契约（/api/control 各 action、/api/executions 字段、meetings SSE 事件格式、mailbox agent 命名、PANEL_TOKEN 优先级、NOVEL_DATA_DIR 环境变量时机、--db 与 set_db_path），全部一致；CSRF/token 防护对浏览器 Origin 与桌面 Node fetch 两条路径均成立。未发现 P0/P1 级阻断问题，5 项发现均为 P2/P3 级（1 个离线空白页、1 个初始加载缺陷、2 个桌面端 UX/内存细节、1 个构建配置失效），不影响现有功能与测试。

Full review comments:

- [P2] SettingsPage 后端不可用时渲染空白页，ErrorState 被短路 — E:\code\novel-editorial\webapp\src\pages\SettingsPage.jsx:39-39
  `webapp/src/pages/SettingsPage.jsx:39` 的 `if (!form) return null;` 位于 113 行 `error ? <ErrorState ...>` 分支之前。`form` 只在 `useEffect` 收到非空 `control` 后才设置；当后端离线（`useApi` 的 `getControl` 抛错，`data` 保持 null）时 `form` 恒为 null，页面直接返回空，用户看不到任何错误提示或重试按钮（复现：mock fetch 全部 reject 后渲染 SettingsPage）。其它页面（DashboardPage、ChaptersPage 等）都会渲染 ErrorState，此处行为不一致。

- [P3] WorksPage 知识库 tab 首次进入永远显示加载中 — E:\code\novel-editorial\webapp\src\pages\WorksPage.jsx:35-45
  `webapp/src/pages/WorksPage.jsx` 中 `loadKnowledge`（35-40 行）只在 `pick()`（42-45 行，点击项目时）调用；初始 `selected = novels[0]` 但 `knowledge` 保持 `null`，190-192 行因此无限渲染 `<LoadingState rows={3}/>`。首次进入作品库页面时「知识库」tab 永远转圈，必须手动点击项目才会加载。

- [P3] vite manualChunks 的 react 条目生成空 chunk，主包未拆分 — E:\code\novel-editorial\webapp\vite.config.js:26-29
  `webapp/vite.config.js:26-29` 的 `manualChunks.react` 配置在当前 vite 7.3.6 构建下失效：`npm run build` 输出 `Generated an empty chunk: "react"`，`react-*.js` 为 0.00 kB，react/react-dom 实际落入主 chunk（853.30 kB / gzip 270.66 kB），只有 charts 成功拆出（396.88 kB）。建议改用 `output.chunkFileNames` 或确认 rolldown-vite 下 manualChunks 的兼容写法。

- [P3] TitleBar 最大化图标状态在系统级最大化时不更新 — E:\code\novel-editorial\webapp\src\components\layout\titlebar.jsx:12-20
  `webapp/src/components/layout/titlebar.jsx:12-13` 只在挂载时查询一次 `desktopApi.isMaximized()`，17-20 行也只在点击最大化按钮后刷新。用户通过双击标题栏、Win+↑ 或拖拽到屏幕边缘最大化窗口时，图标仍显示「最大化」而非「还原」。

- [P3] desktop watchExecutions 的 notifiedExecKeys 无界增长 — E:\code\novel-editorial\desktop\main.js:303-311
  `desktop/main.js:303-311` 中 `notifiedExecKeys` 为每个终止状态的执行添加 `workflow-id-status` key，`markHistory` 与轮询路径均无清理。桌面应用常驻数月后 Set 持续增长（每次执行约几十字节），内存占用虽小但属无界累积，可在轮询时按窗口大小裁剪。
