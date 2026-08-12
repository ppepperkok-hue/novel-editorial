# 修复任务包 · R12-E 测试与配置

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `.env.example`
- `run_tests.py`
- `tests/test_apply_architect.py`（如不存在则新建）

## 修复项

### R12-E-01（P3，新）.env.example:56-63
现状：未记录 NOVEL_DATA_DIR 环境变量。
期望：补录说明（运行时数据目录覆盖，默认值）。

### R12-E-02（P3，新）run_tests.py:10-19
现状：缺少守护 .env.example 与 config 契约的回归测试。
期望：新增测试：.env.example 所有键在 config.py 有消费或标注弃用；config 默认值与示例一致。

### R12-E-03（P3，新）apply_architect.py:214-217
现状：切片内 5 个工具模块缺少直接单元测试（apply_architect 等）。
期望：为 apply_architect 补最小单元测试（merge_blueprints 容错、落盘幂等）；其余 4 个模块在结果中列出测试建议。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`python -m pytest tests/test_apply_architect.py -q`（或新增后运行）；`python run_tests.py` 全绿。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
