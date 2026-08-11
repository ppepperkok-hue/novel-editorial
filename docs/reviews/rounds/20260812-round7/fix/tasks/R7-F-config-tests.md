# 修复任务包 · R7-F 配置与测试

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round7/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tests/test_quality_gate.py`
- `.env.example`

## 修复项

### R7-F-01（P3，新）tests/test_quality_gate.py:35-51
现状：ai_words.json / compliance_words.txt 真实文件内容无守卫测试。
期望：补测试：真实文件存在、可解析、ai_flavor 为 list 且非空；compliance_words.txt 含至少一个有效词。

### R7-F-02（P3，新）.env.example:72-74
现状：遗漏被实际读取的 N8N_WORKFLOW_TRIGGER 与 PYTHONW_EXE 两个键。
期望：补录两键说明与默认值（从代码实际消费确认）。

### R7-F-03（P3，新）.env.example:21
现状：FANQIE_VOLUME_NAME 无任何引用，属死配置。
期望：移除该键（先 rg 确认无引用）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`python -m pytest tests/test_quality_gate.py -q`；.env.example 键唯一性人工核对。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
