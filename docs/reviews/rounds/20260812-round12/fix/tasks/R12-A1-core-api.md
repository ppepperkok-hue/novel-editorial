# 修复任务包 · R12-A1 核心服务与 API

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现 + 第十一轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/daily_runs.py`
- `novel_editorial/web_api.py`

## 修复项

### R12-A1-01（P2，新）daily_runs.py:110-116
现状：sync_from_n8n 不更新已导入运行的状态，成功运行被误标为失败。
期望：已导入运行的状态/时间随最新执行数据更新（幂等更新而非跳过）。

### R12-A1-02（L-066）web_api.py
现状：/api/novel_knowledge upsert 错误返回 200+ok:false，与 save/accept 400 语义不一致。
期望：错误语义统一（400 + 错误信息），或明确文档化差异。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/daily_runs.py novel_editorial/web_api.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
