# 修复任务包 · R4-A2 桌面端

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第四轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round4/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `desktop/main.js`
- `desktop/release.js`

## 修复项

### R4-A2-01（P1）main.js:51-54
现状：桌面版安装到非 C 盘时保存设置必然 500，自动日更失效（路径解析依赖 C 盘）。
期望：路径解析不依赖盘符（用 process.execPath / app.getPath 等真实路径），非 C 盘安装也能保存设置。

### R4-A2-02（P2）release.js:37
现状：发布流程不先构建 webapp，会打包旧前端。
期望：打包前先执行 webapp 构建（npm run build），构建失败则中止发布。

### R4-A2-03（P3）main.js:179
现状：托盘通知不覆盖 partial 状态，部分成功静默无提示。
期望：partial 状态也发通知，文案区分成功/部分/失败。

### R4-A2-04（P3）main.js:122-141
现状：配置 PANEL_TOKEN 后桌面托盘 POST 缺少 Authorization，功能静默失败。
期望：请求携带正确的 Authorization 头（与前端约定一致）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`node --check desktop/main.js desktop/release.js`；如 release.js 有测试则运行；不要实跑发布。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
