# 修复任务包 · R10-A2 编辑部链路

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十轮审查修复（新发现 + 第九轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round10/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/workday.py`
- `tools/editorial_daily.py`
- `tools/agent_meeting.py`
- `tools/architect_weekly.py`

## 修复项

### R10-A2-01（P2，新）workday.py:277
现状：日更模式重复写日记（open 与 close 各写一遍）。
期望：同一工作日只写一次日记（open 或 close 择一，或幂等去重）。

### R10-A2-02（P2，新）editorial_daily.py:1264-1271
现状：重做失败时 _settle_rework 仍把行动项标为 done（假成功）。
期望：重做失败行动项保持非 done（如 failed/pending），并留痕。

### R10-A2-03（P2，新）editorial_daily.py:207
现状：_handle_agency 对散文 Agent 返回 JSON 信封而非正文。
期望：按信封结构解出正文（兼容纯文本与信封），写稿内容不被污染。

### R10-A2-04（P2，新）agent_meeting.py:736-745
现状：--dry-run 仍落库 actions/activity 并执行 apply_report。
期望：dry-run 全路径无持久化副作用（参考 workday/write_diaries 已修模式）。

### R10-A2-05（P3，新）architect_weekly.py:332-333
现状：_safe_int(None) 在缺省设置库上刷 stderr 告警。
期望：None 静默回退默认值（不告警），仅在真异常时告警。

### R10-A2-06（P3，新）editorial_daily.py:913
现状：_meeting_directives 读取的 writing_directives 永无生成方，功能空转。
期望：确认无生成方后移除死读取/或补生成链路（二选一，说明理由）。

### R10-A2-07（L-058）editorial_daily.py / preflight.py
现状：预检失败不写 failed_nodes，链路图无法高亮预检节点。
期望：预检失败时把 preflight 写入 failed_nodes（或等价留痕），链路图可识别。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/workday.py tools/editorial_daily.py tools/agent_meeting.py tools/architect_weekly.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
