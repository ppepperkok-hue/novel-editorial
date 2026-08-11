# 修复任务包 · R5-B 编辑部链路

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第五轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round5/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/workday.py`
- `tools/write_diaries.py`
- `tools/editorial_daily.py`
- `tools/editorial_steps.py`
- `tools/apply_architect.py`
- `tools/meeting_actions.py`

## 修复项

### R5-B-01（P1）workday.py:396-399
现状：缺 __main__ 入口，README 文档化的 CLI 静默无操作。
期望：补 argparse 入口（参考同目录其他工具），支持 --db/--dry-run/run_id 等参数，与 README 文档一致。

### R5-B-02（P2）write_diaries.py:254-256
现状：--dry-run 仍执行 clean_old 删除 56 天前的日记。
期望：dry-run 下跳过所有持久化删除，只输出将做什么。

### R5-B-03（P2）editorial_daily.py:685-689
现状：_apply_writer_responses 读取错误层级，写手响应功能静默失效。
期望：按实际返回结构读取（参考调用方与 mock 数据），功能恢复并留痕。

### R5-B-04（P3）editorial_steps.py:396-400
现状：quality_gate 对非数字 score/hook_rating 直接抛异常，整次日更失败。
期望：非数字输入容错（跳过该项或按 0 处理并留痕），不中断整批。

### R5-B-05（P3）apply_architect.py:18-23
现状：merge_blueprints 对非数字 seq 抛 ValueError，周会决定整体不落盘。
期望：seq 解析容错（默认顺序或跳过留痕），周会决定照常落盘。

### R5-B-06（P3）meeting_actions.py:51-53
现状：幂等标记先于副作用提交，副作用失败后永久不可重试。
期望：副作用成功后提交标记；失败时标记回滚/清理，允许重试。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/workday.py tools/write_diaries.py tools/editorial_daily.py tools/editorial_steps.py tools/apply_architect.py tools/meeting_actions.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
