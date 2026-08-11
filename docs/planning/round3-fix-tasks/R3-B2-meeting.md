# 修复任务包 · R3-B2 会议与报告

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/agent_meeting.py`
- `tools/architect_weekly.py`
- `tools/meeting_actions.py`
- `tools/export_flow_html.py`

## 修复项

### R3-B2-01（P3）agent_meeting.py:252-263
现状：`ask` 工具循环 final round 无重试，单次网络抖动会中断整场会议。
期望：final round 与前面轮次一样支持重试；重试次数上限与现有轮次一致或配置化；重试耗尽才放弃并留痕。

### R3-B2-02（P3）architect_weekly.py:181
现状：周会材料/落盘对 novels.outline 的 JSON 解析无异常保护，脏数据会中断周会。
期望：解析失败时用默认结构（空蓝图/空大纲）继续并留痕，不中断。

### R3-B2-03（P3）meeting_actions.py:33-38
现状：幂等标记检查与插入非原子，并发可重复应用同一会议动作。
期望：用数据库唯一约束或条件插入实现原子幂等（如 INSERT ... WHERE NOT EXISTS / 捕获 IntegrityError），并发下只应用一次。

### R3-B2-04（P3）export_flow_html.py:81-83,125
现状：`groups` 变量是死代码；`daily_runs.status` 未转义直接插入 HTML class 属性。
期望：删除死代码；状态值做白名单映射或 HTML 转义，未知状态落到安全默认 class，不破坏 HTML。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - `python -m compileall tools/agent_meeting.py tools/architect_weekly.py tools/meeting_actions.py tools/export_flow_html.py`
  - 用 `rg` 找 tests 中引用 agent_meeting/architect_weekly/meeting_actions/export_flow_html 的测试，`python -m pytest <相关测试文件> -q` 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
