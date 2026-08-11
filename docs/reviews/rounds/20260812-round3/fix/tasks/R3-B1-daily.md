# 修复任务包 · R3-B1 日更核心

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/editorial_daily.py`
- `tools/workday.py`
- `tools/relations.py`

## 修复项

### R3-B1-01（P2）workday.py:306-309
现状：dry-run 收工/续工仍写入状态机，会真实关闭工作日或阻塞后续 open。
期望：dry_run=True 时所有状态机持久化写都跳过（或显式用内存态），真实运行行为不变。

### R3-B1-02（P3）editorial_daily.py:1160-1167
现状：`rework_applied` 全局标志导致第二个重做请求被静默丢弃且行动项悬置。
期望：去掉全局一次性标志，改为按 run_id/章节/动作维度的幂等键（可查库或按上下文判断）；每个重做请求要么执行要么显式失败留痕，绝不静默丢弃。

### R3-B1-03（P3）editorial_daily.py:1245
现状：发布链 `cover_article` 响应未检查，失败静默继续发布。
期望：检查响应与错误，失败走失败分支/留痕，不静默继续。

### R3-B1-04（P3）editorial_daily.py:621-626
现状：主编分派与重写轮中的 mailroom 调用未检查返回值。
期望：检查返回值，失败显式留痕（日志/结构字段），不静默吞掉。

### R3-B1-05（P3）relations.py:85-88
现状：`decay` 的 days 参数从未使用。
期望：实现衰减真正使用 days（按天数衰减），数值保持 0-1 范围；若参数设计上多余可移除并同步更新本文件内调用方（其他文件的调用方在结果里说明，不改）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - `python -m compileall tools/editorial_daily.py tools/workday.py tools/relations.py`
  - 用 `rg` 找 tests 中引用 editorial_daily/workday/relations 的测试，`python -m pytest <相关测试文件> -q` 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
