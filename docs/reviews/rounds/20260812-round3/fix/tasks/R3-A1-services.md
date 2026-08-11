# 修复任务包 · R3-A1 服务层

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/agency.py`
- `novel_editorial/services/agents.py`
- `novel_editorial/services/control.py`
- `novel_editorial/services/knowledge.py`
- `novel_editorial/services/misc.py`

## 修复项

### R3-A1-01（P1）agency.py:60-98
现状：`_dispatch` 对畸形 action_id 无类型防护，ValueError 会中断整批动作并击穿日更链路。
期望：对非法/非数字/不存在的 action_id 显式校验；单个动作失败只跳过该动作并留痕（日志或结构化错误），绝不中断整批。

### R3-A1-02（P2）agents.py:139-144
现状：`agent_save` 在渲染/校验失败时仍返回 ok=True，造成假绿灯。
期望：失败路径返回 ok=False 并带 error 信息；只有成功才返回 ok=True。

### R3-A1-03（P3）agents.py:39-45
现状：`_extract_node_system` 是无调用方死代码。
期望：先用 `rg` 确认无引用，再删除；若存在测试引用，只删代码并在结果里说明（测试文件不在指派范围）。

### R3-A1-04（P2）control.py:289-290
现状：`apply_schedule` 硬编码 `demo.db`，与 --db 参数及手动触发路径不一致。
期望：DB 路径从配置/环境/传入参数读取，与项目其他路径一致，不硬编码。

### R3-A1-05（P3）knowledge.py:224-228
现状：`update_draft_status` 对 reject/deprecate 也写入 accepted_at。
期望：仅 status 为 accepted 时写 accepted_at；其余状态置 NULL 或保持不动。

### R3-A1-06（P3）misc.py:36-42
现状：`load_hot_topics` 对损坏的 hot_topics.json 无兜底，会拖垮 /api/dashboard。
期望：JSON 损坏时返回空列表/默认结构并记录错误，不抛异常。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - `python -m compileall novel_editorial/services/agency.py novel_editorial/services/agents.py novel_editorial/services/control.py novel_editorial/services/knowledge.py novel_editorial/services/misc.py`
  - 用 `rg` 找 tests 中引用 agency/agents/control/knowledge/misc 的测试，`python -m pytest <相关测试文件> -q` 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
