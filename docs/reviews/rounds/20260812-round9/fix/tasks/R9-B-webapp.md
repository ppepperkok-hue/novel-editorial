# 修复任务包 · R9-B 前端 webapp

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（新发现 + 第八轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round9/slices/slices-summary.md`；第八轮总结遗留节：`docs/reviews/rounds/20260812-round8/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `webapp/src/components/FlowPage.jsx`
- `webapp/src/components/ExecutionsPage.jsx`
- `webapp/src/App.jsx`
- `webapp/src/components/ChaptersPage.jsx`
- `webapp/src/components/SettingsPage.jsx`（如已有测试文件，可新增 `webapp/src/__tests__/settings.test.jsx`）

## 修复项

### R9-B-01（P3，新）ExecutionsPage.jsx:29
现状：snapshot prop 从未使用，SSE 实时快照被丢弃。
期望：消费 snapshot（用于实时更新列表）或移除 prop 并说明；不静默丢弃。

### R9-B-02（P3，新）App.jsx:101-102
现状：快捷键帮助文案声称 1–12，实际数字键只能直达 1–9。
期望：文案与实际能力一致（1–9 + 其余入口说明）。

### R9-B-03（P3，新）App.jsx:60
现状：fetchControl 轮询错误被吞，侧边栏调度器状态短暂假绿灯。
期望：轮询失败时侧边栏显示错误/未知状态，不假绿灯。

### R9-B-04（P3，新）ChaptersPage.jsx:76-78
现状：章节正文加载失败被静默伪装成「正文未落库」，误导用户。
期望：区分加载失败与未落库两种状态，失败显示错误与重试。

### R9-B-05（P3，新）SettingsPage.jsx
现状：关键交互页面与 desktop 主进程无自动化测试覆盖。
期望：新增 settings 渲染/交互冒烟测试（设置保存失败提示、计划任务注册失败可见）。

### R9-B-06（遗留）FlowPage.jsx:63
现状：className 仍拿整体 status 给所有节点上色，未消费新的 node_status。
期望：消费 node_status 逐节点上色（与 R8-B2 后端口径一致）。

### R9-B-07（遗留）ExecutionsPage.jsx
现状：fmt 死代码；空状态 colSpan=7 vs 表头 6 列；toggleRun 失败无提示。
期望：删死代码；colSpan 修正；失败提示。

### R9-B-08（遗留）workday.close ok 消费方检查
现状：workday.close 的 ok 语义变化（failed/partial 返回 ok=False），面板/后端消费方需核对。
期望：用 rg 找 webapp 与后端对 close/ok 的消费点，若面板把 ok 当「关闭动作成功」则需调整；只改本组文件内的消费方，其他消费方在结果中说明。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写。
- 验证：在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
