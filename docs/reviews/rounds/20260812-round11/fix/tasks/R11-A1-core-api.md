# 修复任务包 · R11-A1 核心服务与 API

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十一轮审查修复（新发现 + 第十轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round11/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/meeting_session.py`
- `novel_editorial/pipeline.py`
- `novel_editorial/web_api.py`

## 修复项

### R11-A1-01（P2，新）meeting_session.py:31-54
现状：create_session 并发竞态可创建多个 running 会议会话。
期望：并发创建互斥（唯一约束/条件插入/锁），同类型会话不重复创建 running。

### R11-A1-02（P3，新）pipeline.py:1-5
现状：DEPRECATED 模块无生产调用方，与新链路双轨并存。
期望：确认无引用（含 tests）后删除或移入 tools/archive；有引用则说明。

### R11-A1-03（L-059）web_api.py
现状：knowledge_drafts accept 分支 write_knowledge 的 ValueError 未捕获（仍 500）。
期望：与 save 分支一致捕获返回 400。

### R11-A1-04（L-060）web_api.py
现状：/api/knowledge、/api/knowledge_drafts、/api/novel_knowledge 三个分支 conn 未关闭。
期望：所有分支 finally 关闭连接，不泄漏。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/services/meeting_session.py novel_editorial/pipeline.py novel_editorial/web_api.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
