# 修复任务包 · R6-F 配置与测试

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第六轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round6/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `.env.example`
- `compliance_words.txt`
- `novel_editorial/quality_gate.py`
- `tests/test_quality_gate.py`
- `run_tests.py`

## 修复项

### R6-F-01（P2）.env.example:71-72
现状：行内注释导致配置静默回退失效。
期望：去掉行内注释或改为独立注释行，确保键值可被正常解析。

### R6-F-02（P3）quality_gate.py:33-34
现状：对 ai_words.json 缺失/损坏静默回退无告警。
期望：缺失/损坏时告警（warnings 或日志），与 compliance 容错对称。

### R6-F-03（P3）tests/test_quality_gate.py:14-16
现状：未钉住重叠词非重叠计数语义。
期望：补用例：重叠词（如 缓缓/缓缓说道）只计一次；空词表返回 0。

### R6-F-04（P3）run_tests.py:8-11
现状：不收集 *_test.py 命名测试。
期望：discover 同时覆盖 test_*.py 与 *_test.py（或说明排除原因）。

### R6-F-05（P3）.env.example:54-56
现状：硬编码真实 n8n 工作流 ID。
期望：替换为占位符（如 your-workflow-id），注明从面板获取。

### R6-F-06（P3）compliance_words.txt
现状：全注释，发布扫描每次触发 EMPTY 警告。
期望：在词库中填入若干真实通用违规词（保留注释示例），或调整扫描逻辑对空词库不再每次告警（二选一，说明理由）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 本组允许修改 tests/test_quality_gate.py（补测试守护）。
- 验证：`python -m compileall novel_editorial/quality_gate.py`；`python -m pytest tests/test_quality_gate.py tests/test_compliance.py -q`；`python run_tests.py` 需继续全绿。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
