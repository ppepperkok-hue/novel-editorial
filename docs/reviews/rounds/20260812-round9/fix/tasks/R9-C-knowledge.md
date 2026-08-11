# 修复任务包 · R9-C 知识体系遗留

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（第八轮遗留跟进）。第八轮总结遗留节：`docs/reviews/rounds/20260812-round8/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/novel_knowledge.py`
- `tools/knowledge_keeper.py`
- `tools/clean_novel_knowledge.py`

## 修复项

### R9-C-01（遗留）novel_knowledge.py / knowledge_keeper.py
现状：_parse_json 用首尾花括号截取，LLM 输出字符串值含花括号会截错。
期望：截取逻辑改为平衡花括号扫描或 json 解码容错（尝试完整解析，失败再截取），值内花括号不截错。

### R9-C-02（遗留）knowledge_keeper.py
现状：读热点 JSON 为 list 时 hot.get 直接崩溃。
期望：热点文件解析后校验 dict，非 dict 回退默认并留痕。

### R9-C-03（遗留）clean_novel_knowledge.py
现状：备份文件名只精确到秒，同一秒跑两次 --apply 互相覆盖。
期望：文件名加毫秒/随机后缀，同秒重跑不覆盖。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/novel_knowledge.py tools/knowledge_keeper.py tools/clean_novel_knowledge.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
