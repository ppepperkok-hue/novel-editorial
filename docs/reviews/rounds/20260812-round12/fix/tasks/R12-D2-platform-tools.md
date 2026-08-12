# 修复任务包 · R12-D2 平台工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/create_book.py`
- `tools/n8n_api.py`
- `scripts/inject_fanqie_cookie.py`
- `scripts/start_n8n.ps1`

## 修复项

### R12-D2-01（P3，新）create_book.py:342-344
现状：网络错误后无幂等保护，重复执行可能重复建书。
期望：建书幂等（按 book_id/标题去重或失败留痕可重试），不重复建。

### R12-D2-02（P3，新）n8n_api.py:96-97
现状：无参数运行抛 IndexError。
期望：无参数时输出用法并明确退出（非崩溃）。

### R12-D2-03（P3，新）inject_fanqie_cookie.py:17-21 / start_n8n.ps1
现状：.env 解析与 config.load_env 分歧（行内注释/引号处理不一致）。
期望：复用 config 解析逻辑或对齐语义（行内注释、值内 # 不截断）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/create_book.py tools/n8n_api.py scripts/inject_fanqie_cookie.py`；ps1 用 PowerShell 5.1 解析校验；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
