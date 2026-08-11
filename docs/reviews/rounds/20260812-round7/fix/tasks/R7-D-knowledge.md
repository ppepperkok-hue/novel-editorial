# 修复任务包 · R7-D 知识体系遗留

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（遗留跟进）。遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/novel_knowledge.py`
- `tools/export_agent_prompts.py`

## 修复项

### R7-D-01（L-019）novel_knowledge.py
现状：upsert_ex 对 content 相同但 change_note 非空的调用仍 version+1。
期望：内容未变化时不 version+1（change_note 仅在有实际变更时落），避免 history 膨胀。

### R7-D-02（L-026）novel_knowledge.py
现状：冲突草稿书隔离靠 title 前缀，长期应给 knowledge_drafts 加 novel_id 列。
期望：给 knowledge_drafts 增加 novel_id 列（幂等迁移），查重/插入按 novel_id 隔离；旧数据兼容（前缀兜底）。

### R7-D-03（L-033）novel_knowledge.py
现状：sync_latest 两条路径结构差 count 键（无章节路径带 count，有章节路径没有）。
期望：两条路径结构统一（都含 count 或都移除，以消费方为准）。

### R7-D-04（L-034）novel_knowledge.py
现状：_add_conflict_draft 的 category 参数未使用。
期望：使用该参数写入草稿（如类别字段），或删除参数并更新调用方（只限本文件）。

### R7-D-05（L-017）export_agent_prompts.py
现状：END_MARK 若出现在 system 正文内部会被提前截断。
期望：截断判定加保护（如只在独立行匹配 END_MARK），正文内的 END_MARK 不截断。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/novel_knowledge.py tools/export_agent_prompts.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
