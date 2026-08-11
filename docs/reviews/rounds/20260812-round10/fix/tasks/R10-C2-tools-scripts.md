# 修复任务包 · R10-C2 工具脚本遗留

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十轮审查修复（新发现 + 第九轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round10/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `scripts/_run_fix_worker.ps1`
- `tools/n8n_api.py`
- `tools/delete_book.py`

## 修复项

### R10-C2-01（P3，新 + L-054）_run_fix_worker.ps1:34-50
现状：任务文本中的双引号未转义，可破坏 node 命令行（第九轮 D2 曾因此失败）；且整段文本作单条命令行参数。
期望：任务文本写入临时文件、codex 从 stdin 读取（`-` 参数），彻底避免引号/长度问题；临时文件用完即删。

### R10-C2-02（L-053）n8n_api.py
现状：手工 Cookie 头与 CookieJar 重复附加风险；token 静默作废时缓存继续用旧值。
期望：完全依赖 CookieJar（不手工塞 Cookie 头）；token 缓存有效期或每次校验，避免陈旧。

### R10-C2-03（L-055）delete_book.py
现状：reply_to 回复链 ref_novel_id/ref_chapter_id 全 0 时消息残留（极少见边角）。
期望：删除书时对 ref 全 0 且归属本书的回复链消息兜底清理（如按 thread/会话归属）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/n8n_api.py tools/delete_book.py`；ps1 用 PowerShell 5.1 解析校验，并用含双引号的中文任务文本实测一次派发（dry-run 层面）。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
