# 修复任务包 · R6-D 知识体系

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第六轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round6/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/novel_knowledge.py`

## 修复项

### R6-D-01（P3）novel_knowledge.py:601-608
现状：sync_latest 两条路径返回结构不一致，无章节分支缺少 skipped 键。
期望：两路径返回结构统一（都含 skipped），无章节时 skipped 为空列表。

### R6-D-02（P3）novel_knowledge.py:412-415
现状：world_events 缺类型守卫，LLM 输出 dict 时事件被静默丢弃且无留痕。
期望：与 character_states 对称的类型校验，非 list 时跳过并留痕（skipped），不静默。

### R6-D-03（P3）novel_knowledge.py:114-119
现状：冲突草稿 title 前缀使升级前旧数据无法命中新去重查询，可能重复建草稿。
期望：查重同时兼容旧格式（无前缀）与新格式（有前缀），不重复建草稿。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/novel_knowledge.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
