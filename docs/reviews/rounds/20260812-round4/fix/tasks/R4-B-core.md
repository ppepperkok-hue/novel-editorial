# 修复任务包 · R4-B 核心服务层

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第四轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round4/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/services/activity.py`
- `novel_editorial/services/meeting_session.py`
- `novel_editorial/services/control.py`
- `novel_editorial/services/n8n.py`
- `novel_editorial/backup.py`
- `novel_editorial/desktop.py`

## 修复项

### R4-B-01（P2）activity.py:324-326
现状：字符串 action_items 使会后任务生成整体失败。
期望：兼容字符串与列表两种输入（字符串按分隔拆分或显式类型校验），失败留痕不中断。

### R4-B-02（P2）meeting_session.py:99-101
现状：会议心跳 10 分钟阈值会误杀仍在运行的会话。
期望：阈值放宽或改为可配置，长会议不被误判为失活。

### R4-B-03（P3）control.py:356
现状：触发周会会污染日更防重复标志 manual_run_requested。
期望：周会触发与日更防重复标志隔离，互不污染。

### R4-B-04（P3）n8n.py:52-58
现状：n8n API key 进程内永久缓存，改 env 后不生效。
期望：每次读取或提供刷新机制，env 变更后生效。

### R4-B-05（P3）backup.py:31
现状：keep=0 时实际不删除任何旧备份。
期望：keep=0 语义为不保留旧备份（删除全部旧备份），实现与语义一致。

### R4-B-06（P3）desktop.py:36-41
现状：pick_port 候选端口全占用时未捕获绑定异常。
期望：捕获绑定异常并尝试下一候选，全部失败返回明确错误。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/services/activity.py novel_editorial/services/meeting_session.py novel_editorial/services/control.py novel_editorial/services/n8n.py novel_editorial/backup.py novel_editorial/desktop.py`；用 `rg` 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
