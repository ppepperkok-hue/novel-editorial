# 修复任务包 · R6-C 桌面与前端

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第六轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round6/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `desktop/main.js`
- `webapp/src/App.jsx`
- `webapp/.npmrc`

## 修复项

### R6-C-01（P2）main.js:206-218
现状：桌面端每次启动都会对最近 30 条终态执行补发系统通知。
期望：启动时只对「本次启动期间」变化的执行发通知；已通知过的执行持久化或仅启动后新终态通知，不补发历史。

### R6-C-02（P3）App.jsx:59-70
现状：手动刷新不再更新 dashboardError，失败静默、恢复后错误横幅最多残留 5 秒。
期望：手动刷新成功清除错误横幅、失败设置错误状态；与轮询路径一致。

### R6-C-03（P3）webapp/.npmrc:1
现状：提交了本机绝对路径缓存目录。
期望：移除本机绝对路径；需要缓存配置时用相对/通用值或删除该文件。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`node --check desktop/main.js`；在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
