# 修复任务包 · R11-C 知识体系

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十一轮审查修复（新发现 + 第十轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round11/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/export_agent_prompts.py`
- `tools/ai_taste_check.py`
- `tools/distill_lessons.py`
- `tools/novel_knowledge.py`
- `tools/knowledge_keeper.py`

## 修复项

### R11-C-01（P2，新）export_agent_prompts.py:63-68
现状：proxy 模式下永不导出却返回成功（假绿灯）。
期望：proxy 模式显式说明不导出或实现导出，绝不返回假成功。

### R11-C-02（P3，新）ai_taste_check.py:94-107
现状：四字排比启发式对普通叙述误报、对真实排比漏报。
期望：修正启发式（连续同类结构判定），减少误报漏报。

### R11-C-03（P3，新）ai_taste_check.py:30
现状：漏检常见写法「不是……而是」（双省略号）。
期望：词表/模式补充该写法。

### R11-C-04（P3，新）distill_lessons.py:265-270
现状：空 lessons 列表静默返回成功。
期望：空列表显式标记（警告/失败），不假成功。

### R11-C-05（L-062 + 新）novel_knowledge.py:251-253
现状：get() 的 entity 参数未转义 LIKE 通配符（resolve 已修，get 同类）。
期望：get 的 LIKE 参数同样转义。

### R11-C-06（P3，新）knowledge_keeper.py:196-202
现状：未校验 LLM 输出的 JSON schema。
期望：输出结构校验（必须 dict 且关键键类型正确），非法时回退并留痕。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/export_agent_prompts.py tools/ai_taste_check.py tools/distill_lessons.py tools/novel_knowledge.py tools/knowledge_keeper.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
