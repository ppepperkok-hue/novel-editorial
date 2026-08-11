# 修复任务包 · R4-A1 前端 webapp

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第四轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round4/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `webapp/src/components/SettingsPage.jsx`
- `webapp/src/components/AgentsPage.jsx`
- `webapp/src/components/Shell.jsx`
- `webapp/vite.config.js`

## 修复项

### R4-A1-01（P0）SettingsPage.jsx:82-89
现状：保存设置时 Windows 计划任务注册静默失败，自动日更永不触发——前端未检查后端返回，把失败当成功。
期望：保存后检查响应；计划任务注册失败时显示明确错误（区分设置已保存与任务注册失败），不静默。

### R4-A1-02（P2）AgentsPage.jsx:171-181
现状：Agent 保存失败时校验详情分支不可达，用户看不到失败原因。
期望：修复条件/字段引用，失败时展示 render 与 validation 详情。

### R4-A1-03（P3）Shell.jsx:141
现状：快捷键帮助文案「1 – 8」与实际导航项数量不符。
期望：文案与真实导航项数量一致（或动态生成）。

### R4-A1-04（P3）vite.config.js:1-20
现状：vite dev 模式无代理，npm run dev 无法联调后端 API。
期望：配置 /api 代理到后端 web_api 实际端口（从项目代码确认端口，参考 novel_editorial/web_api.py 或 config）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：在 `webapp` 目录 `npx vitest run`；`npm run build` 通过。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
