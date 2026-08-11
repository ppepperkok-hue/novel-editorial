# 修复任务包 · R7-E 平台工具与文档

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（遗留跟进）。遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/publish_stock.py`
- `scripts/watch_daily.py`
- `novel_editorial/services/ending.py`
- `README.md`
- `n8n/README.md`
- 测试卫生：找出 desktop/release 与 exports/archive 下导致 pytest 收集 SystemExit 的测试文件，加守护或从自动收集排除（改动仅限这些测试文件或其父 __init__/conftest）

## 修复项

### R7-E-01（L-022）publish_stock.py
现状：status=finishing 但 finish_remaining=0 的极端数据会照单全发而不收尾。
期望：finish_remaining<=0 时视为已完结，不发布并收尾/报错。

### R7-E-02（L-021）watch_daily.py
现状：cost_logs 为空时 cost_today 打印 None。
期望：空数据显示 0 或占位，不打印 None。

### R7-E-03（L-023）ending.py
现状：Path 死导入。
期望：删除未使用导入。

### R7-E-04（L-020）README.md
现状：仍列 finish_rename.ps1（已归档），描述过时。
期望：移除/更新过时条目，与当前仓库结构一致。

### R7-E-05（L-028）README.md / n8n/README.md
现状：仍把 MONTHLY_BUDGET 等死配置键当有效配置写。
期望：移除或标注已弃用，与 .env.example 一致。

### R7-E-06（L-015）测试卫生
现状：web_api 全量 pytest 收集被 desktop/release 与 exports/archive 下导入期 SystemExit 的测试文件干扰。
期望：这些测试文件加「仅手动运行」守护（如 sys.exit 改为 pytest.skip）或从自动收集排除，`pytest --collect-only` 无 SystemExit。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`python -m compileall tools/publish_stock.py scripts/watch_daily.py novel_editorial/services/ending.py`；`python -m pytest --collect-only -q` 无 SystemExit；README 改动人工核对。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
