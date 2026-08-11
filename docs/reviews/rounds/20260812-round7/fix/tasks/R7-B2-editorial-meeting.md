# 修复任务包 · R7-B2 会议与报告

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（新发现 + 遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round7/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/agent_meeting.py`
- `tools/meeting_actions.py`
- `tools/export_flow_html.py`
- `tools/flow_graph.py`

## 修复项

### R7-B2-01（P2，新）agent_meeting.py
现状：选题会(planning)在已有作品时被绑定到最新小说，apply_report 会改写该书数据。
期望：planning 会议不绑定具体小说（或按会议 kind 区分），不改写已有书数据。

### R7-B2-02（P2，新）agent_meeting.py
现状：CLI 轮次循环无异常隔离，LLM 失败中止整场会议并遗留 running 会话。
期望：单轮失败隔离（跳过该轮并留痕），会议可继续；异常时清理/标记会话。

### R7-B2-03（P3，新）export_flow_html.py
现状：未映射 skipped 状态，最近一次跳过运行显示为「待命（暂无运行）」。
期望：skipped 映射为独立样式/文案（如「已跳过」）。

### R7-B2-04（P3，新）flow_graph.py
现状：FAILED_ALIAS 缺少 eic，主编分派失败无法在链路图中高亮。
期望：FAILED_ALIAS 增加 eic（及分派相关别名）。

### R7-B2-05（L-009）agent_meeting.py
现状：ask 内重复 import 顶层已有的 knowledge。
期望：删除重复 import，用已有引用。

### R7-B2-06（L-008）meeting_actions.py
现状：config 死导入。
期望：删除未使用导入。

### R7-B2-07（L-025）meeting_actions.py
现状：audit.log 每次自提交，重试可能重复写 review/critique 审计行。
期望：审计写入与幂等标记同事务（或去重），重试不重复审计。

### R7-B2-08（L-010）export_flow_html.py
现状：JS 端 STATUS 无白名单，奇怪状态会污染 class 和颜色（DOM 赋值安全但显示脏）。
期望：JS 端状态也做白名单映射（与 Python 端一致）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/agent_meeting.py tools/meeting_actions.py tools/export_flow_html.py tools/flow_graph.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
