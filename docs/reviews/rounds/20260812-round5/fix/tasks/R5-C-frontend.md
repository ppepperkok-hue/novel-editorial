# 修复任务包 · R5-C 桌面与前端

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第五轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round5/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `desktop/release.js`
- `desktop/main.js`
- `webapp/src/App.jsx`

## 修复项

### R5-C-01（P1）release.js:44-46
现状：uploads ASCII exe whose name differs from latest.yml path, breaking auto-update（上传的 exe 文件名与 latest.yml 记录路径不一致，自动更新失败）。
期望：上传文件名与 latest.yml 中记录一致（去掉非 ASCII 或统一命名），发布产物可被自动更新发现。

### R5-C-02（P1）main.js:52-55
现状：demo.db 被放进 resources 目录，NSIS 升级会覆盖并清空用户运行数据。
期望：运行数据与安装目录隔离（用户数据目录），升级不覆盖；种子库只在首次启动时复制。

### R5-C-03（P2）main.js:241-249
现状：ensureApi 失败后应用仍在运行但无窗口无托盘。
期望：失败时显示错误并退出，或保持托盘并显示错误状态，不留无头进程。

### R5-C-04（P3）main.js:196-209
现状：watchExecutions 只跟踪 list[0]，终止通知可能漏报。
期望：遍历全部执行记录，逐条发通知。

### R5-C-05（P3）App.jsx:62-65
现状：refresh() 在 fetch 完成前就重置 refreshing 标志，重复请求可能并发。
期望：fetch 完成后（finally）再重置标志。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`node --check desktop/release.js desktop/main.js`；在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
