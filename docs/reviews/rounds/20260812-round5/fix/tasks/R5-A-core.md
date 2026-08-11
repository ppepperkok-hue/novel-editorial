# 修复任务包 · R5-A 核心服务层

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第五轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round5/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/activity.py`
- `novel_editorial/services/ending.py`
- `novel_editorial/services/control.py`
- `novel_editorial/services/meeting_session.py`
- `novel_editorial/services/n8n.py`（死代码删除，见 R5-A-05）

## 修复项

### R5-A-01（P2）activity.py:263-273
现状：_normalize_action_items 把 JSON 数组字符串（如 action_items 是 JSON 文本）拆成碎片任务。
期望：先尝试 json.loads，若是列表则按元素解析；字符串再按分隔符拆分；不产生碎片任务。

### R5-A-02（P2）ending.py:51-68
现状：bind_book 先提交 DB 再写 ~/.n8n/.env，目录缺失时状态半更新（DB 已绑定但 env 未写）。
期望：先确保 env 文件可写（目录存在/可创建）再提交 DB；或失败时回滚 DB 状态并留痕。

### R5-A-03（P2）control.py:289-294
现状：apply_schedule 跨盘符 os.path.relpath 抛 ValueError 导致 500。
期望：跨盘时用绝对路径或容错处理，不抛 500。

### R5-A-04（P3）meeting_session.py:324-330
现状：run_session 注释声称用会话库，实际忽略行的 db_path 回退 demo.db。
期望：实际使用会话行携带的 db_path，注释与行为一致。

### R5-A-05（P3）services/n8n.py:1-6
现状：services/n8n.py 全仓库无调用方，属死代码。
期望：先用 rg 确认无引用（含 tests），再删除文件；若有引用则说明并保留。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/services/activity.py novel_editorial/services/ending.py novel_editorial/services/control.py novel_editorial/services/meeting_session.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
