验证基线通过：desktop/main.js 与 preload.js 通过 node --check，webapp `npm run build` 成功（仅 500kB chunk 体积警告）。主要功能契约（web_api/control/agents/activity/meeting 等前后端接口）核对一致，未发现确定性崩溃或数据损坏。但存在 1 个 P1（安装包打包 104MB 浏览器会话数据，含 Login Data，已随已构建的 1.0.0 产物出现，发布前必须修复）与 1 个 P2（启动窗口期二次启动产生双窗口），另 4 个 P3 级健壮性/UX 问题，因此不能判定为完全正确。

Full review comments:

- [P1] 安装包打包 tools/chrome-profile 泄漏浏览器会话数据 — E:\code\novel-editorial\desktop\package.json:31-37
  desktop/package.json 的 build.extraResources.filter 含 "tools/**"（第 37 行），会把整个 tools 目录打进安装程序，其中包括 tools/chrome-profile/（104MB 真实 Chrome 用户数据）。已构建产物 desktop/release/win-unpacked/resources/novel-pipeline/tools/chrome-profile/ 存在且 Default/Login Data（40960B）、History、Web Data、Session Storage 均被打包；release.js 随后会把 setup exe 上传到公开 GitHub Releases。后果：开发机的番茄作家后台登录态/密码库随安装包公开分发，且安装包被撑大 100+MB。建议在 filter 中排除 tools/chrome-profile（以及 tools 下其他运行时目录），或把 filter 改为显式白名单。

- [P2] 启动窗口期内二次启动会创建第二个窗口且第一个窗口泄漏 — E:\code\novel-editorial\desktop\main.js:269-285
  desktop/main.js 的 app.whenReady 在 await ensureApi()（第 273 行）期间已注册 second-instance 处理器（第 269 行），此时 win 为 null，showWindow() 会提前调用 createWindow()；ensureApi 完成后第 285 行又无条件 createWindow()，win 引用被新窗口覆盖，第一个 BrowserWindow 未被销毁且无引用，用户会看到两个窗口。触发条件：应用启动的几秒~20 秒窗口内再次启动程序（双击图标/快捷键），API 冷启动越慢越容易触发。createWindow（第 84 行）缺少 `if (win) return` 守卫。

- [P3] 输入框内按问号键会弹出帮助弹窗 — E:\code\novel-editorial\webapp\src\App.jsx:101-105
  webapp/src/App.jsx 的全局 keydown 处理器中 `if (e.key === "?")`（第 101 行）在输入框豁免检查（第 105 行）之前执行，因此在任何 input/textarea 中敲 `?`（如设置页输入题材、搜索框）都会打开/关闭快捷键帮助弹窗，与帮助文案宣称的"输入框内不触发页面切换"意图相悖。应把 `?` 分支移到 tag 豁免判断之后。

- [P3] AI 味检测失败后无法重试 — E:\code\novel-editorial\webapp\src\components\ChaptersPage.jsx:81-86
  webapp/src/components/ChaptersPage.jsx 的 checkTaste 中，检测失败会 setTaste({ score: -1, notes: ["检测失败"] })，而入口守卫 `if (!reader || taste) return`（第 81 行）使 taste 非空后永远无法再次发起检测，用户只能关闭阅读器重开。建议失败时把 taste 重置回 null（或区分 loading/error 状态）以允许重试。

- [P3] WorksPage 多处 getEndingStatus().then() 缺少 catch — E:\code\novel-editorial\webapp\src\components\WorksPage.jsx:302-302
  webapp/src/components/WorksPage.jsx 第 302/325/360/518 行的 `getEndingStatus().then(...)` 均无 .catch，后端不可达或返回非 2xx 时 getJSON 抛错，产生 unhandled promise rejection，结束状态卡片不会刷新（用户无感知失败）。建议统一加 .catch(() => {}) 或在成功后刷新处补充。

- [P3] 后端 API 进程运行期崩溃后桌面端无感知、不自动恢复 — E:\code\novel-editorial\desktop\main.js:71-75
  desktop/main.js 中 apiProc.on("error") 只向渲染进程发送 "api-error"（第 74 行），但 preload.js 与 webapp 前端均无该事件监听者，属于死代码；同时 apiProc 没有注册 "exit" 处理，pythonw 在运行中崩溃（如未捕获异常、OOM）后托盘无任何通知，watchExecutions 持续静默轮询失败，窗口长期停留在"无法连接后端服务"，只能手动退出重开。建议监听 exit 事件并通过 Notification 提示用户。
