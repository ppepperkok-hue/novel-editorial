# 修复任务包 · R3-D 前端桌面

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `webapp/src/components/AgentsPage.jsx`
- `webapp/src/components/WorksPage.jsx`
- `webapp/src/components/FlowPage.jsx`
- `webapp/src/api.js`
- `webapp/src/App.jsx`
- `desktop/package.json`

## 修复项

### R3-D-01（P2）AgentsPage.jsx:127-137
现状：心情面板读写使用不同 agent key，保存后永远无法回显。
期望：读写统一使用同一个 agent key（对照接口字段与保存请求体），保存后可正常回显。

### R3-D-02（P2）WorksPage.jsx:352-357
现状：手动绑定书请求失败时按钮永久卡在「绑定中」。
期望：请求无论成败都恢复按钮状态，并在失败时显示错误提示。

### R3-D-03（P3）api.js:10-16
现状：多处按钮直接 await postJSON 无 catch，后端离线时静默失败且无提示。
期望：在 api.js 层统一处理网络错误（抛出可识别错误或返回错误结构），并让调用方（本组组件内）显示提示；避免重复包裹已处理处。

### R3-D-04（P3）App.jsx:139-141
现状：后端离线时 App 永久显示骨架屏，连接错误提示不可见。
期望：初始请求失败时渲染连接错误状态与重试按钮，不再永久骨架屏。

### R3-D-05（P3）FlowPage.jsx:6-8
现状：重复定义 API_BASE，属死代码。
期望：删除本地重复定义，改用统一导入（与项目其他页面一致）。

### R3-D-06（P2）desktop/package.json:31-41
现状：桌面打包版保存每日时间后，计划任务指向资源目录种子库且脚本未打包。
期望：打包版计划任务使用用户数据目录下的数据库；安装计划任务所需脚本纳入打包（extraResources 等），路径在打包环境正确解析。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - 在 `webapp` 目录下 `npx vitest run`（如环境变量 TEMP/TMP 指向 E:\code\.tmp 可避免空间问题）。
  - `npm run build` 需能通过；如构建时间过长，至少保证 vitest 全绿并说明 build 未跑。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
