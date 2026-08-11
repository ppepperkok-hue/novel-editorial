# 修复任务包 · R9-D2 平台工具与脚本

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（新发现）。审查报告：`docs/reviews/rounds/20260812-round9/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/n8n_api.py`
- `scripts/watch_daily.py`
- `tools/delete_book.py`
- `scripts/_run_fix_worker.ps1`
- `pyproject.toml`

## 修复项

### R9-D2-01（P3，新）n8n_api.py:49
现状：每次请求重复登录（session cookie 未复用）。
期望：登录会话缓存/复用（同进程内），批量操作不重复登录；失败时重新登录一次。

### R9-D2-02（P3，新）watch_daily.py:35
现状：监控标签偏差（状态标签与 daily_runs 实际状态不一致）。
期望：标签与状态映射一致（对照 daily_runs 状态值）。

### R9-D2-03（P3，新）delete_book.py:70-95
现状：删除绑定番茄的书后孤儿消息残留（agent_messages 等关联未清理）。
期望：删除书时同步清理 agent_messages/agent_relations 等关联数据（参考 _purge_novel 已有清理清单补齐）。

### R9-D2-04（P3，新）_run_fix_worker.ps1
现状：未指定 -Model 时构造空 -m 参数；任务文件过大时命令行超限。
期望：Model 为空时不传 -m；任务文本超长（如 >15000 字符）时报错提示拆分，不静默截断。

### R9-D2-05（P3，新）pyproject.toml:6
现状：包元数据乱码（编码问题）。
期望：修正为正确 UTF-8 元数据；`pip show` 显示正常。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/n8n_api.py scripts/watch_daily.py tools/delete_book.py`；ps1 用 PowerShell 5.1 解析校验；pyproject 用 python 的 tomllib 读取校验可解析（验证命令自行构造，注意：本任务文本经命令行传参，任何命令都禁止出现英文双引号）。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
