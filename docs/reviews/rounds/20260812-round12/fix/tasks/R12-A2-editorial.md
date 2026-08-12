# 修复任务包 · R12-A2 编辑部链路

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现 + 第十一轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/editorial_daily.py`
- `tools/agent_meeting.py`

## 修复项

### R12-A2-01（P2，新）editorial_daily.py:944-959
现状：_review_tone 查询方向与写入方向相反，摩擦语气永不生效。
期望：查询方向与写入一致（对照 agent_relations 写入方），摩擦影响语气实际生效。

### R12-A2-02（P3，新）editorial_daily.py:1670-1685
现状：daily(chapters=N) 在生成链上不生效，请求 1 章仍产出 2 章。
期望：chapters 参数真实控制产出章数（各轨按目标章数生成）。

### R12-A2-03（P3，新）agent_meeting.py:626-639
现状：--dry-run 仍会落库伪造的会议记录（会话行）。
期望：dry-run 不落任何库（与 R10-A2-04 全链无副作用一致），仅内存运行。

### R12-A2-04（P3，新 + 核实）agent_meeting.py:280-308
现状：compress_history 声称无调用方；上轮核验称 meeting_session.py:484 调用。
期望：用 rg 全仓核实真实调用方；真无调用则删除，有调用则保留并在结果说明。

### R12-A2-05（L-065）agent_meeting.py
现状：CLI 路径直接 INSERT running 会话，绕过 create_session 并发锁。
期望：CLI 创建收敛到 create_session 统一入口（或等效互斥），与 web_api 并发不双开。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/editorial_daily.py tools/agent_meeting.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
