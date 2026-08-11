# 修复任务包 · R8-A1 核心服务与 API

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（新发现 + 第七轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round8/slices/slices-summary.md`；第七轮总结遗留节：`docs/reviews/rounds/20260812-round7/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/web_api.py`
- `novel_editorial/services/meeting_session.py`
- `novel_editorial/services/agency.py`

## 修复项

### R8-A1-01（P3，新）meeting_session.py:357-360
现状：_run_locked 抛 RuntimeError 不落盘，会议错误对用户不可感知。
期望：异常落盘（标记 failed + audit 留痕），错误可见。

### R8-A1-02（遗留）web_api.py
现状：do_POST 对合法但非对象 JSON（数组/字符串）仍 500。
期望：顶层必须是 dict，否则 400。

### R8-A1-03（遗留）web_api.py
现状：/api/agent_states/update 的 novel_id 未整数清洗，非整数以文本落 INTEGER 列。
期望：novel_id 整数清洗，非法 400。

### R8-A1-04（遗留）meeting_session.py
现状：create_session 仍把 planning 绑最新书，_run_locked 对非 0 novel_id 仍调 apply_report（planning 根因）。
期望：planning 会议 novel_id=0 不绑书，_run_locked 对 planning 不调 apply_report（与 R7-B2-01 的 agent_meeting 侧对齐）。

### R8-A1-05（遗留）meeting_session.py
现状：_run_locked 的 materials is None 分支标记 failed 但无 audit 留痕。
期望：补 audit 留痕。

### R8-A1-06（遗留）agency.py
现状：apply 中非 dict action 项只计 rejected 不写 audit。
期望：非 dict 项写 audit（带原因）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/web_api.py novel_editorial/services/meeting_session.py novel_editorial/services/agency.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
