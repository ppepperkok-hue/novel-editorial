# 修复任务包 · R10-B 平台工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round10/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/publish_stock.py`
- `tools/check_stock.py`
- `tools/collect_reader_stats.py`
- `tools/get_meta.py`
- `tools/release_lock.py`

## 修复项

### R10-B-01（P2，新）publish_stock.py:427-433
现状：部分发布成功后仍清零 pending_publish，剩余章节静默丢失。
期望：部分成功时按实际发布数递减 pending_publish（或保留失败部分），剩余章节可续发。

### R10-B-02（P2，新）check_stock.py:25-30
现状：默认按全库统计存稿，与 publish_stock 的活跃书范围不一致。
期望：默认统计范围与发布一致（活跃书），范围差异显式说明。

### R10-B-03（P2，新）collect_reader_stats.py:135-144
现状：缺失的完读/追读率写成 0.0，误导低质章节反馈。
期望：缺失值用 NULL/空标记（不写 0.0），消费方按缺失处理。

### R10-B-04（P3，新）get_meta.py:74-86
现状：读取非对象结构的 hot_topics.json 时 AttributeError 崩溃。
期望：非 dict 结构回退默认并留痕，不崩溃。

### R10-B-05（P3，新）release_lock.py:17-22
现状：不校验锁归属，可误删并发运行持有的锁。
期望：锁内记录持有者信息（pid/任务），释放前校验归属；不匹配时拒绝。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/publish_stock.py tools/check_stock.py tools/collect_reader_stats.py tools/get_meta.py tools/release_lock.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
