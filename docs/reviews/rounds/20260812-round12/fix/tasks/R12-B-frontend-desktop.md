# 修复任务包 · R12-B 前端与桌面

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现 + 第十一轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `desktop/main.js`
- `desktop/release.js`
- `webapp/src/components/CommandPalette.jsx`

## 修复项

### R12-B-01（P2，新 + L-068 桌面侧）main.js:82-93
现状：桌面版锁文件仍写入安装目录，未随 NOVEL_DATA_DIR 迁移，只读安装导致应用拒绝启动。
期望：锁文件路径迁移到运行时数据目录（与 dataDir 一致）。

### R12-B-02（P3，新）release.js:83-89
现状：陈旧版本检查在 gh 失败时静默失效，可能重建同版本 Release。
期望：gh 失败时显式报错中止发布（不静默放行）。

### R12-B-03（P3，新）CommandPalette.jsx:63-72
现状：触发 run-daily/run-weekly 后不刷新面板数据，与其它操作不一致。
期望：执行后触发刷新（与其它入口一致）。

### R12-B-04（P3，新 + L-069）main.js:127-143
现状：api-error IPC 与 preload closeToTray 均为无消费方死代码。
期望：核实 preload/webapp 引用；无消费方则删除，或补齐桥接让错误真正到达页面。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`node --check desktop/main.js desktop/release.js`；在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
