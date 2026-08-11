# 修复任务包 · R3-E1 AI 味质量门

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/quality_gate.py`
- `tools/ai_taste_check.py`

## 修复项

### R3-E1-01（P2）quality_gate.py:50
现状：style 分低估，AI 味密度虚高最多 2 倍；与另两个消费方计数不一致。
期望：统一「AI 味词命中计数/密度」的计算口径（词表、匹配方式、归一化与 tools/ai_taste_check.py 及另一个消费方一致），style 分不再系统性低估。改动后以现有测试和手工样例验证密度值一致。

### R3-E1-02（P3）tools/ai_taste_check.py:48-53
现状：修复无回归保护，词表变更会静默改变密度。
期望：把词表匹配/密度计算抽成可独立测试的纯函数（在本文件内完成），并在最终结果中给出明确的测试用例建议（测试文件不在指派范围，不要改测试文件）；保证现有行为对合法词表稳定。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - `python -m compileall novel_editorial/quality_gate.py tools/ai_taste_check.py`
  - 用 `rg` 找 tests 中引用 quality_gate/ai_taste_check 的测试，`python -m pytest <相关测试文件> -q` 运行。
  - 手工构造含「缓缓说道/微微一愣」等词的样例，确认三个消费方（quality_gate style 分、ai_taste_check、另一个消费方）密度一致。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
