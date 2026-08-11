# 修复任务包 · R3-E2 配置与合规词库

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `.env.example`
- `compliance_words.txt`
- `novel_editorial/compliance.py`

## 修复项

### R3-E2-01（P3）.env.example:34-35,58-59
现状：存在重复键，且 setdefault 先值生效，用户改后一组会被静默忽略。
期望：去重合并为单组键；保留完整默认值与注释，标注哪个生效。

### R3-E2-02（P3）.env.example
现状：MEETING_MODE、N8N_*、AGENT_CTX_* 等键无文档。
期望：为这些键补简短说明（用途、可选值、默认值），与现有注释风格一致。

### R3-E2-03（P3）compliance_words.txt / novel_editorial/compliance.py
现状：词库为空时无告警，真实文件无测试覆盖。
期望：compliance.py 在词库为空/全注释时给出显式告警（日志或返回结构带 warning），不静默用空词库；检查词库文件是否为空并如实报告。测试文件不在指派范围，测试建议写入最终结果。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- `.env.example` 是文档性配置，改动后人工核对键不丢失、注释完整。
- 验证：
  - `python -m compileall novel_editorial/compliance.py`
  - 用 `rg` 找 tests 中引用 compliance 的测试，`python -m pytest <相关测试文件> -q` 运行。
  - 手工核对 .env.example 无重复键、新增注释渲染正常。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
