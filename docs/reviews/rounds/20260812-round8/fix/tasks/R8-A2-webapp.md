# 修复任务包 · R8-A2 前端 webapp

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（新发现 + 遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round8/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `webapp/src/components/ExecutionsPage.jsx`（或执行记录页对应文件，以实际文件名为准）
- `webapp/src/__tests__/dashboard.test.jsx`

## 修复项

### R8-A2-01（P3，新 + 遗留合并）ExecutionsPage
现状：/api/daily_runs 返回的 sync_error 字段前端未展示，n8n 同步失败仍对用户静默。
期望：执行记录页展示 sync_error（错误横幅/区块），有错误时可见。

### R8-A2-02（P3，新）dashboard.test.jsx:1-12
现状：dashboard 测试只覆盖 helper 未覆盖页面渲染。
期望：补页面渲染冒烟测试（渲染不抛错、关键区块存在）；如组件可测性差，先重构最小可测单元。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
