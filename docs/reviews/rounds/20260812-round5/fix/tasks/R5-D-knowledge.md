# 修复任务包 · R5-D 知识体系

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第五轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round5/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/novel_knowledge.py`
- `tools/distill_lessons.py`
- `tools/clean_novel_knowledge.py`
- `tools/knowledge_keeper.py`

## 修复项

### R5-D-01（P1）novel_knowledge.py sync_from_chapters
现状：对 character_states 缺类型防御，LLM 输出数组时整批同步崩溃。
期望：类型校验（必须 dict），非 dict 时跳过该项并留痕，不中断整批。

### R5-D-02（P2）distill_lessons.py session 分支
现状：硬编码 attendees/kind，丢弃已存参会者信息。
期望：从会话记录读取真实 attendees/kind，硬编码兜底仅用于缺失时。

### R5-D-03（P3）clean_novel_knowledge.py
现状：--dry-run 参数从未读取，属死参数；备份文件名硬编码 demo- 前缀。
期望：实现 --dry-run（只报告不落库），备份文件名按小说/库名生成。

### R5-D-04（P3）novel_knowledge.py sync_latest
现状：DISTINCT+ORDER BY 依赖 SQLite 未定义行为。
期望：改为稳定排序（显式 ORDER BY 完整键或先聚合再排序）。

### R5-D-05（P3）novel_knowledge.py 冲突草稿
现状：冲突草稿按 title 去重，跨小说同名实体漏建草稿。
期望：去重键包含 novel_id（或按书隔离），跨书同名不误并。

### R5-D-06（P3）knowledge_keeper.py / distill_lessons.py
现状：对 usage 字段无空值防御。
期望：usage 缺失/为空时安全处理（默认值），不抛异常。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/novel_knowledge.py tools/distill_lessons.py tools/clean_novel_knowledge.py tools/knowledge_keeper.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
