# 修复任务包 · R9-D1 平台核心

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（新发现 + 第八轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round9/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/record_work.py`
- `tools/check_stock.py`
- `tools/publish_stock.py`
- `tools/preflight.py`

## 修复项

### R9-D1-01（P1，新）record_work.py:466
现状：月度成本低估 50%+，预算闸门失真（成本统计口径问题）。
期望：核对成本聚合口径（是否漏计或重复除权），修复后与 cost_logs 实际一致；附验证数字。

### R9-D1-02（P2，新）record_work.py:341
现状：上游 seq 为非数字字符串时归档崩溃、n8n 裸 traceback。
期望：seq 解析容错（默认值 + 留痕），不崩溃。

### R9-D1-03（P3，新）check_stock.py / publish_stock.py
现状：用户显式设置 0 章仍发 1 章。
期望：设置 0 表示不发布（尊重显式 0，与未设置默认区分）。

### R9-D1-04（P3，新）preflight.py:48
现状：cookie 值混入注释（.env 含内联注释时按注释截断）。
期望：与 config.load_env 一致处理行内注释边界（值内 # 不截断），cookie 不被截断。

### R9-D1-05（遗留）preflight.py
现状：顶层 LOCK_FILE 常量（daily.lock）与实际 {db stem}.lock 不一致，容易误导。
期望：统一常量与实现（或移除误导常量，改函数动态计算）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/record_work.py tools/check_stock.py tools/publish_stock.py tools/preflight.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
