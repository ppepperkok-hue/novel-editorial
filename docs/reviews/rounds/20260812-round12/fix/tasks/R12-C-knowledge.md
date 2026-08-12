# 修复任务包 · R12-C 知识体系

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现 + 第十一轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/novel_knowledge.py`
- `tools/clean_novel_knowledge.py`
- `tools/distill_lessons.py`
- `tools/knowledge_keeper.py`
- `tools/export_agent_prompts.py`

## 修复项

### R12-C-01（P1，新）novel_knowledge.py:230-237
现状：upsert_ex 并发更新时重复写入 history，审计链被污染。
期望：history 写入原子化（唯一约束/事务内检查），并发下不重复。

### R12-C-02（P1，新）clean_novel_knowledge.py:194-201
现状：链式相似规则合并时静默丢失整行内容。
期望：合并保留全部内容（与 R4-C-03 同款保留策略），不静默丢弃。

### R12-C-03（P2，新）clean_novel_knowledge.py:266-274
现状：删除无 item 对应的 power/金手指，唯一设定记录丢失。
期望：无 item 对应的设定保留或显式询问，不静默删唯一记录。

### R12-C-04（P3，新）distill_lessons.py:86-104
现状：对 report/transcript 的非预期 JSON 类型无防御，直接崩溃。
期望：类型校验（dict/list），非法回退并留痕。

### R12-C-05（P3，新）novel_knowledge.py:195
现状：upsert_ex 合并判定基于截断 120 字符的 content，长内容相似实体永不合并。
期望：判定基于完整内容（或提高截断并说明权衡），长内容可合并。

### R12-C-06（P3，新）knowledge_keeper.py:242-243
现状：对非 market 文件的 auto_updates 静默跳过，无日志无审计。
期望：跳过时留痕（audit/日志），不静默。

### R12-C-07（P3，新 + L-070）export_agent_prompts.py:63-68
现状：proxy 模式 exit 1 使脚本化调用误判失败（上轮改为诚实失败，但语义过重）。
期望：proxy 模式明确区分「不支持」与「失败」：输出说明且退出码 0（或不导出但非错误），文档同步。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/novel_knowledge.py tools/clean_novel_knowledge.py tools/distill_lessons.py tools/knowledge_keeper.py tools/export_agent_prompts.py`；用 rg 找相关测试并 pytest 运行；并发 history 用双线程实测。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
