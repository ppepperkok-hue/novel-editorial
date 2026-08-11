# 修复任务包 · R10-A1 核心服务与 API

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十轮审查修复（新发现 + 第九轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round10/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/hot_topics.py`
- `novel_editorial/services/misc.py`
- `novel_editorial/services/knowledge.py`
- `novel_editorial/web_api.py`
- `novel_editorial/services/ending.py`
- `novel_editorial/services/meeting_session.py`

## 修复项

### R10-A1-01（P2，新）hot_topics.py:287-291
现状：固定临时文件名并发写盘竞态。
期望：临时文件用唯一名（pid/随机后缀）或原子写（写临时+rename），并发不互相覆盖。

### R10-A1-02（P3，新 + L-048）misc.py:136
现状：load_meetings 的 topics 字段 JSON 解析缺少容错（attendees 已修，topics 同类风险）。
期望：topics 解析失败回退空列表并留痕，不 500；report 解析失败也补留痕。

### R10-A1-03（P3，新）knowledge.py:82-87
现状：write_knowledge 仅校验 title/source/updated_at，type 可注入换行破坏 frontmatter。
期望：type（及所有写入 frontmatter 的字段）禁止换行/控制字符，非法输入拒绝或清洗。

### R10-A1-04（P3，新）web_api.py:911
现状：POST /api/knowledge save 中 write_knowledge 的 ValueError 未捕获，返回 500。
期望：捕获 ValueError 返回 400 带错误信息。

### R10-A1-05（P3，新）ending.py:51-57
现状：bind_book 的 book_id 未清洗换行，可向 ~/.n8n/.env 注入额外配置行。
期望：book_id 清洗换行/控制字符，禁止注入。

### R10-A1-06（P3，新）meeting_session.py:311-312
现状：会议 outbox 单条消息 chapter_id/reply_to 非整数会丢弃该 agent 全部外发邮件。
期望：单条消息容错（非法 id 跳过该条并留痕），不影响其余消息。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/hot_topics.py novel_editorial/services/misc.py novel_editorial/services/knowledge.py novel_editorial/web_api.py novel_editorial/services/ending.py novel_editorial/services/meeting_session.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
