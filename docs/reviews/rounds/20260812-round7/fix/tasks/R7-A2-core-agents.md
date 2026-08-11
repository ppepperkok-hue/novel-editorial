# 修复任务包 · R7-A2 代理与状态

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（遗留跟进）。遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/agents.py`
- `novel_editorial/services/agency.py`
- `novel_editorial/seed_demo.py`
- `novel_editorial/services/meeting_session.py`

## 修复项

### R7-A2-01（L-001）agents.py
现状：agent_save 的 I/O 异常未捕获，回滚只覆盖 returncode 非 0 分支；read_text/write_text 与 subprocess OSError 时文件已写却不回滚。
期望：读写与渲染全路径异常捕获；任何失败都回滚原文件并返回 ok=False 带 error。

### R7-A2-02（L-002）agency.py
现状：claim_task 被拒的具体原因（action not found、已认领、畸形 id）未进 audit detail，只记 ok=False。
期望：audit detail 增加拒绝原因字段（reason），追踪性完整。

### R7-A2-03（L-005）seed_demo.py
现状：seed 对负数参数无校验。
期望：负数参数校验（报错或 clamp），不产生非法状态。

### R7-A2-04（L-029）meeting_session.py
现状：_run_locked 在会话行不存在时仍静默 return（显式 db_path 指错库时无提示）。
期望：行不存在时显式抛错/标记 failed 并留痕，不静默。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/services/agents.py novel_editorial/services/agency.py novel_editorial/seed_demo.py novel_editorial/services/meeting_session.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
