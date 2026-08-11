# 修复任务包 · R6-E 平台工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第六轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round6/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/record_work.py`
- `tools/get_meta.py`
- `tools/collect_reader_stats.py`
- `tools/preflight.py`
- `tools/n8n_api.py`

## 修复项

### R6-E-01（P1）record_work.py:166
现状：对非 dict 的 character_updates 抛 AttributeError，当日归档静默丢失。
期望：类型校验（必须 dict 或 list），非预期类型时跳过并留痕，不中断归档。

### R6-E-02（P2）get_meta.py:72
现状：对合法 JSON 但形状错误的 outline/tags 崩溃，违反自身 _safe_json 契约。
期望：_safe_json 后增加形状校验（dict/list），形状错误回退默认并留痕。

### R6-E-03（P3）collect_reader_stats.py:147-152
现状：无匹配章节时用空表覆盖 reader_stats.csv，静默清空既有反馈数据。
期望：无匹配时不写空表（保留原数据），或先备份再写；不静默清空。

### R6-E-04（P3）preflight.py:151-155
现状：acquire_lock 文档与实现的 2 小时陈旧规则互相矛盾。
期望：文档与实现统一（按实际行为改文档或按文档改实现）。

### R6-E-05（P3）n8n_api.py:12
现状：硬编码 localhost:5678 与触发器名，忽略 N8N_BASE 配置。
期望：读取 N8N_BASE/N8N_WORKFLOW_* 配置（有默认值），不再硬编码。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/record_work.py tools/get_meta.py tools/collect_reader_stats.py tools/preflight.py tools/n8n_api.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
