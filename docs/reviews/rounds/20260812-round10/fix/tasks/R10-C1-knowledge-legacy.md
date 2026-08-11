# 修复任务包 · R10-C1 知识遗留

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十轮审查修复（第九轮遗留跟进）。遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/distill_lessons.py`
- `tools/knowledge_keeper.py`
- `tools/novel_knowledge.py`
- `tools/ai_taste_check.py`
- `tools/record_work.py`

## 修复项

### R10-C1-01（L-049）distill_lessons.py:26-30
现状：首尾花括号截取函数（与 knowledge_keeper 已修版同病，LLM 值内花括号截错）。
期望：与 knowledge_keeper 同款平衡花括号扫描（或复用同一实现）。

### R10-C1-02（L-050）knowledge_keeper.py
现状：热点 sources 非 list 时 s.get 崩溃。
期望：sources 类型校验（必须 list），非 list 回退空并留痕。

### R10-C1-03（L-051）novel_knowledge.py
现状：resolve 对 LIKE 通配符 %/_ 未转义；docstring 示例与 CLI 不符。
期望：LIKE 参数转义通配符；docstring 与实际 CLI 参数一致。

### R10-C1-04（L-056）ai_taste_check.py
现状：detect 对非字符串输入抛 TypeError（假值已覆盖，列表等未覆盖）。
期望：非字符串输入显式校验（回退空结果或 TypeError 转 ValueError 带说明），不裸崩。

### R10-C1-05（L-052）record_work.py
现状：upsert_chapters 对元素无 dict 防线，混入字符串/None 整段崩溃。
期望：元素类型校验（必须 dict），非 dict 跳过并留痕。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/distill_lessons.py tools/knowledge_keeper.py tools/novel_knowledge.py tools/ai_taste_check.py tools/record_work.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
