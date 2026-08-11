# 修复任务包 · R11-D 平台工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十一轮审查修复（新发现 + 第十轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round11/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/create_book.py`
- `tools/preflight.py`
- `tools/publish_stock.py`
- `tools/record_work.py`
- `tools/collect_reader_stats.py`
- `tools/get_meta.py`

## 修复项

### R11-D-01（P2，新）create_book.py:271-272
现状：对字符串形状 protagonists 抛未捕获 AttributeError。
期望：protagonists 类型校验（list/dict），字符串或非法形状清洗/回退并留痕。

### R11-D-02（P3，新）preflight.py:227
现状：already_ran 为全局检查，与 per-book 声明不一致。
期望：按书维度检查（与声明的 per-book 语义一致），或文档化全局语义。

### R11-D-03（P3，新）publish_stock.py:379-388
现状：db.connect 失败时运行锁残留且异常裸奔。
期望：连接失败时释放锁并返回明确错误。

### R11-D-04（P3，新）record_work.py:356
现状：章节 status 缺失时默认 published，产生虚假成功发布记录。
期望：status 缺失显式标记（unknown/skip），不默认 published。

### R11-D-05（L-063）record_work.py
现状：record_payload 活动统计对 chapters 元素 c.get 裸调；upsert_characters 无 dict 防线。
期望：元素类型校验与安全取值，非 dict 跳过并留痕。

### R11-D-06（P3，新）collect_reader_stats.py:69
现状：仅拉取第一页 200 章，超长书无翻页。
期望：支持翻页拉取全部章节（或明确限制并留痕）。

### R11-D-07（L-064）get_meta.py
现状：sources 为 dict 时 src.get 崩溃；top_keywords 非 list 无校验。
期望：sources/top_keywords 类型校验，非法回退并留痕。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/create_book.py tools/preflight.py tools/publish_stock.py tools/record_work.py tools/collect_reader_stats.py tools/get_meta.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
