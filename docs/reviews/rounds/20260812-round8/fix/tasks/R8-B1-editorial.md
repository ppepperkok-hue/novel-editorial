# 修复任务包 · R8-B1 编辑部链路

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（新发现 + 第七轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round8/slices/slices-summary.md`；第七轮总结遗留节：`docs/reviews/rounds/20260812-round7/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/agent_meeting.py`
- `tools/editorial_daily.py`
- `tools/mailroom.py`
- `tools/write_diaries.py`
- `tools/architect_weekly.py`
- `tools/workday.py`

## 修复项

### R8-B1-01（P2，新）agent_meeting.py:736-743
现状：会后行动项硬编码 session_id=0，丢失会议关联。
期望：使用真实会议 session_id 写行动项。

### R8-B1-02（P2，新）editorial_daily.py:1659-1664
现状：预检失败路径不清零 pending_publish 一次性覆盖。
期望：预检失败时 pending_publish 保持或显式处理，不静默覆盖。

### R8-B1-03（P3，新）mailroom.py:167
现状：resolve 错误消息遗漏合法 resolution 值。
期望：错误消息列出合法值（accepted/rejected/done）。

### R8-B1-04（P3，新）write_diaries.py:297
现状：库调用时 print 污染调用方 stdout。
期望：改为日志/结构化返回，不 print。

### R8-B1-05（P3，新）architect_weekly.py:284-289
现状：本周章节判定在 novels.updated_at 为空时计入全部章节。
期望：updated_at 为空时安全处理（按创建时间或排除），不误计全部。

### R8-B1-06（遗留）agent_meeting.py / meeting_actions.py
现状：run_post_actions 幂等「先查后插」，并发双跑可能重复应用。
期望：加唯一约束或条件插入根治并发窗口（meeting_actions.py 不在本组文件列表则说明并留到下轮）。

### R8-B1-07（遗留）editorial_daily.py
现状：_dispatch 读关系快照仍只取 other 列，旧迁移行空 key。
期望：兼容 other/other_agent（同 R7-B1-04 模式）。

### R8-B1-08（遗留）workday.py
现状：close 最终 failed/partial 仍返回 ok=True，CLI exit 0。
期望：业务失败（failed/partial）时返回 ok=False 或 CLI 非 0（保持面板语义不破坏）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/agent_meeting.py tools/editorial_daily.py tools/mailroom.py tools/write_diaries.py tools/architect_weekly.py tools/workday.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
