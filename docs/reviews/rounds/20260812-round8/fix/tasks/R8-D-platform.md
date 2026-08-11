# 修复任务包 · R8-D 平台工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round8/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/get_meta.py`
- `tools/record_work.py`
- `tools/check_stock.py`
- `tools/preflight.py`
- `tools/publish_stock.py`

## 修复项

### R8-D-01（P1，新）get_meta.py:133-136
现状：对 bible.characters 非 dict 元素崩溃，日更上下文静默丢失。
期望：元素类型校验（必须 dict），非 dict 跳过并留痕。

### R8-D-02（P2，新）record_work.py:306-307
现状：对非 int words/prompt_tokens 崩溃导致整次归档失败。
期望：int() 容错（默认 0 + 留痕），不中断归档。

### R8-D-03（P2，新）record_work.py:235-242
现状：同 run_id 重复归档产生重复伏笔/演化/事件行。
期望：按 run_id 幂等（先删后插或更新），重复归档不产生重复行。

### R8-D-04（P3，新）check_stock.py:48-51
现状：默认分支不识别 finishing 状态书，收尾期查存稿返回空。
期望：finishing 状态也纳入存稿查询。

### R8-D-05（P3，新）preflight.py:253-258
现状：CLI 在未持有运行锁时消费 manual_run_requested。
期望：仅在持有锁/预检通过时消费该标志，避免误消费。

### R8-D-06（P3，新）publish_stock.py:357-361
现状：CLI 入口不检查运行锁，可绕过防双发保护。
期望：入口检查运行锁（参考 preflight/release_lock），有锁则拒绝。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/get_meta.py tools/record_work.py tools/check_stock.py tools/preflight.py tools/publish_stock.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
