# 修复任务包 · R5-F 配置与测试守护

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第五轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round5/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/quality_gate.py`
- `novel_editorial/compliance.py`
- `tests/test_compliance.py`
- `.env.example`

## 修复项

### R5-F-01（P3）quality_gate.py:20-25
现状：加载 ai_flavor 缺 isinstance 校验，字符串值会按单字符计 AI 味密度。
期望：校验为 list；非 list 时回退内置词表并告警，不逐字符计。

### R5-F-02（P3）compliance.py:62-71
现状：_read_custom_words 无异常捕获，坏编码词库文件直接穿透发布前扫描。
期望：读取/解码失败时捕获并告警（warnings），扫描用内置词继续，不崩溃。

### R5-F-03（P3）tests/test_compliance.py:23-29
现状：空词库告警逻辑与真实数据文件均无测试守护。
期望：补测试：词库缺失/空/全注释时有 warnings；有自定义词时无 warnings（测试文件本次可以修改）。

### R5-F-04（P3）.env.example
现状：遗漏被实际消费的 REVIEW_RETRY_MAX 与 MEETING_HEARTBEAT_TIMEOUT_MINUTES；死配置键 MONTHLY_BUDGET/N8N_HOST/N8N_LISTEN_ADDRESS/N8N_PASSWORD 误导用户。
期望：补两个被消费键的说明；死配置键加「已弃用/无效」标注或移除（以代码实际消费为准）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 本组允许修改 tests/test_compliance.py（补测试守护）。
- 验证：`python -m compileall novel_editorial/quality_gate.py novel_editorial/compliance.py`；`python -m pytest tests/test_compliance.py -q`；手工核对 .env.example 键说明。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
