# 修复任务包 · R9-A1 核心服务与 API

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round9/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/meeting_session.py`
- `novel_editorial/web_api.py`
- `novel_editorial/services/misc.py`

## 修复项

### R9-A1-01（P2，新）meeting_session.py:579-587
现状：会议等待输入循环缺少 failed 状态退出条件，线程永久轮询。
期望：会话状态为 failed 时退出循环并清理，不永久轮询。

### R9-A1-02（P2，新）web_api.py:1179-1181
现状：_fail_orphan_sessions 误杀等待输入的会议，转录与报告丢失。
期望：等待输入（awaiting_input）的会话不被判为孤儿失败（仅清理 running 且超时的）。

### R9-A1-03（P3，新）meeting_session.py:113
现状：get_active_session 对 NULL heartbeat_at 抛 TypeError，会议端点 500。
期望：NULL heartbeat 安全处理（视为活跃或用当前时间），不 500。

### R9-A1-04（P3，新）web_api.py:56-61
现状：_origin_allowed 放行无端口本地 origin，可绕过面板 token 写保护。
期望：无端口本地 origin 不自动放行（或仅放行明确白名单），写保护不被绕过。

### R9-A1-05（P3，新）misc.py:116
现状：load_meetings 解析 attendees 无异常保护，损坏数据导致 500。
期望：attendees 解析失败回退空列表并留痕，不 500。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/services/meeting_session.py novel_editorial/web_api.py novel_editorial/services/misc.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
