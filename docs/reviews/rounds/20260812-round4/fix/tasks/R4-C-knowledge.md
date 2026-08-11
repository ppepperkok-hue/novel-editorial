# 修复任务包 · R4-C 知识体系

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第四轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round4/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/clean_novel_knowledge.py`
- `tools/novel_knowledge.py`
- `tools/knowledge_keeper.py`
- `tools/export_agent_prompts.py`

## 修复项

### R4-C-01（P1）clean_novel_knowledge.py:203-211
现状：--apply 在多个实体收敛到同一规范名时崩溃。
期望：冲突时合并或跳过并留痕，绝不崩溃。

### R4-C-02（P1）novel_knowledge.py:196-200
现状：sync_from_chapters 重复同步仍无限 version+1 并膨胀 history 表。
期望：内容无变化时幂等，不新增 version/history。

### R4-C-03（P2）clean_novel_knowledge.py:184-200
现状：_merge_history 静默丢弃被合并行的 content，相似但内容不同的设定丢失。
期望：保留/合并被合并行内容（拼接或结构化保留），不静默丢弃。

### R4-C-04（P3）knowledge_keeper.py:158-183
现状：自动更新无内容变化检测，每次运行都重写知识包并刷新 updated_at。
期望：内容无变化时不重写、不刷新 updated_at。

### R4-C-05（P3）export_agent_prompts.py:60-73
现状：非代理导出路径对 find() 无 -1 保护，格式不符时静默写坏文件。
期望：find 失败时明确报错/跳过，不写坏文件。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/clean_novel_knowledge.py tools/novel_knowledge.py tools/knowledge_keeper.py tools/export_agent_prompts.py`；用 `rg` 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
