# 修复任务包 · R8-C 知识体系

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round8/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/novel_knowledge.py`
- `tools/knowledge_keeper.py`
- `tools/distill_lessons.py`
- `tools/clean_novel_knowledge.py`
- `tools/ai_taste_check.py`

## 修复项

### R8-C-01（P1，新）novel_knowledge.py:615
现状：sync_latest 对非法 JSON outline 无防御，知识库同步整体中断。
期望：outline 解析失败回退默认结构并留痕，不中断同步。

### R8-C-02（P2，新）knowledge_keeper.py:160-161
现状：知识管家/蒸馏对 LLM 输出数组元素类型零校验，字符串元素直接 AttributeError 崩溃。
期望：元素类型校验（必须 dict），非 dict 跳过并留痕。

### R8-C-03（P2，新）distill_lessons.py:178-182
现状：对无 lessons 键的合法 JSON 返回 ok:True，假绿灯。
期望：无 lessons 键视为失败或空结果并明确标记，不假绿灯。

### R8-C-04（P2，新）clean_novel_knowledge.py:309-312
现状：WAL 模式下用 shutil.copy2 备份，备份文件缺失已提交数据。
期望：备份前 checkpoint（PRAGMA wal_checkpoint）或使用 sqlite backup API，确保备份完整。

### R8-C-05（P3，新）ai_taste_check.py:70-72
现状：detect 空文本返回值缺少 chars 键，输出 schema 不一致。
期望：空文本也返回 chars 键（0），schema 统一。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/novel_knowledge.py tools/knowledge_keeper.py tools/distill_lessons.py tools/clean_novel_knowledge.py tools/ai_taste_check.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
