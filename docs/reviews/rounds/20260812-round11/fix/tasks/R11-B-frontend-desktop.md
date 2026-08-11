# 修复任务包 · R11-B 前端与桌面

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十一轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round11/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `desktop/main.js`
- `desktop/release.js`
- `desktop/package.json`
- `webapp/src/components/AgentsPage.jsx`
- `novel_editorial/config.py`

## 修复项

### R11-B-01（P2，新）main.js / config.py / package.json
现状：只读安装目录下 hot-topics、weekly lock、exports、alerts 静默失败，UI 报成功。
期望：写操作失败时检测并向 UI 透出错误（不假成功）；数据目录可写性启动时校验。

### R11-B-02（P2，新）release.js / package.json / main.js
现状：版本不手动 bump，自动更新通道永久陈旧。
期望：发布流程自动 bump 版本（读取当前版本 +1 或校验与 latest.yml 一致），不发布陈旧版本。

### R11-B-03（P2，新）AgentsPage.jsx
现状：编辑心情后切换 agent 再保存，错写另一 agent 的心情并注入提示词。
期望：保存锁定当前编辑的 agent（切换时提示/重置），绝不写错 agent。

### R11-B-04（P3，新）main.js
现状：3 次 API 崩溃后自动重启永久禁用。
期望：冷却期后重置计数（如 10 分钟无崩溃恢复自愈），或提供手动重置入口。

### R11-B-05（P3，新）config.py
现状：PANEL_TOKEN 行内 # 注释导致托盘请求 403。
期望：config 解析兼容行内注释（复用 _strip_inline_comment），PANEL_TOKEN 不截断。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`node --check desktop/main.js desktop/release.js`；package.json JSON 校验；在 webapp 目录 `npx vitest run` 与 `npm run build`。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
