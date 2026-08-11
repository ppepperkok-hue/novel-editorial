# 修复任务包 · R11-A2 编辑部链路

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十一轮审查修复（新发现 + 第十轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round11/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/editorial_daily.py`
- `tools/workday.py`
- `tools/export_flow_html.py`
- `tools/agent_meeting.py`

## 修复项

### R11-A2-01（P1，新）editorial_daily.py:1160
现状：重做失败返回 original passed gate 且带失败重写文本（gate-bypass）。
期望：重做失败时质量门不得通过（failed gate + 失败原因），不发布失败文本。

### R11-A2-02（P2，新）workday.py:110-121
现状：org/meeting 模式绕过 active-run guard，可两个并发工作日。
期望：所有模式共享活跃运行锁/守卫，org/meeting 也不能并发开日。

### R11-A2-03（P2，新）workday.py:239
现状：进程在 opening 阶段死亡时工作日永久卡死。
期望：opening 陈旧行可被回收（参照 daily_runs 陈旧回收），不永久卡死。

### R11-A2-04（P3，新）editorial_daily.py:218-235
现状：全局（novel_id=0）消息被注入但从不标已读。
期望：注入后按约定标读（与业务消息一致），不无限累积。

### R11-A2-05（P3，新）export_flow_html.py:71-88
现状：completed_with_pending 状态渲染为 idle（待命）。
期望：映射为已完成/待办样式，不与 idle 混淆。

### R11-A2-06（P3，新）agent_meeting.py:618-621
现状：CLI topic/planning 会议用周会议程标签。
期望：按会议 kind 使用正确议程标签（topic/planning 非 weekly）。

### R11-A2-07（P3，新）agent_meeting.py:280
现状：compress_history 死代码（从不调用）。
期望：确认后删除或接入调用点。

### R11-A2-08（L-061）workday.py
现状：resume 路径可能重复写日记（close 已去重）。
期望：resume 触发收尾链时同样按日记已存在去重。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/editorial_daily.py tools/workday.py tools/export_flow_html.py tools/agent_meeting.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
