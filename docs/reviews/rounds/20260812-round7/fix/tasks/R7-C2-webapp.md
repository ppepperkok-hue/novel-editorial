# 修复任务包 · R7-C2 前端 webapp

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（新发现 + 遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round7/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `webapp/src/App.jsx`
- `webapp/src/components/ChaptersPage.jsx`
- `webapp/src/components/WorksPage.jsx`
- `webapp/src/components/SettingsPage.jsx`

## 修复项

### R7-C2-01（P3，新）App.jsx:101-105
现状：输入框内按问号键会弹出帮助弹窗。
期望：全局快捷键忽略输入框/文本域聚焦状态（或在输入态不触发）。

### R7-C2-02（P3，新）ChaptersPage.jsx:81-86
现状：AI 味检测失败后无法重试（按钮状态不恢复或缺少重试入口）。
期望：失败后可重试，按钮状态恢复并显示错误。

### R7-C2-03（P3，新）WorksPage.jsx:302
现状：多处 getEndingStatus().then() 缺少 catch。
期望：补 catch（复用项目统一错误处理），不静默。

### R7-C2-04（L-032）App.jsx
现状：usePolling 返回的 error 不再被消费（dashboardError 本地维护后冗余）。
期望：统一错误消费路径，删除冗余或合并状态。

### R7-C2-05（L-013）SettingsPage.jsx
现状：action()/save() 无显式 catch（postJSON 已包 ok:false，风险低）。
期望：补兜底 catch 并显示错误，保证任何失败可见。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
