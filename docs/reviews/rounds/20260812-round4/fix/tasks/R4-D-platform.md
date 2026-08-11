# 修复任务包 · R4-D 平台与部署

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第四轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round4/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/record_work.py`
- `tools/publish_stock.py`
- `pyproject.toml` 与 `uv.lock`
- `tools/n8n_api.py`
- `scripts/watch_daily.py`
- `scripts/install_daily_task.ps1`
- `scripts/finish_rename.ps1`（仅移动到 `tools/archive/`，不提交）

## 修复项

### R4-D-01（P1）record_work.py:315-322
现状：二次记录同一章时 qrow[scores] 抛 IndexError。
期望：按章节幂等更新，二次记录不崩溃且正确覆盖/合并。

### R4-D-02（P2）publish_stock.py:290-311
现状：书已标记 finished 后仍继续发布超额章节。
期望：finished 后立即停止，超额章节留在存稿。

### R4-D-03（P2）pyproject.toml:10
现状：声明 websocket-client 但 uv.lock 未更新，uv sync 会失败。
期望：运行 `uv lock` 更新 uv.lock（仅更新 lock 文件），uv sync 可成功。

### R4-D-04（P3）n8n_api.py:7-9
现状：模块级读取 N8N_TMP_PW，未加载 ~/.n8n/.env 且报错无提示。
期望：延迟读取并加载所需 env，缺失时给出明确提示。

### R4-D-05（P3）watch_daily.py:21-22
现状：daily_runs 无记录时访问 exec[status] 抛 KeyError。
期望：无记录时安全返回默认状态。

### R4-D-06（P3）install_daily_task.ps1:33-34
现状：-Remove 不检查 schtasks 退出码，误报删除成功。
期望：检查退出码，失败时输出错误并返回非 0。

### R4-D-07（P3）finish_rename.ps1:15-18
现状：遗留重命名脚本硬编码 E:\code 绝对路径且已完成使命。
期望：移动到 `tools/archive/finish_rename.ps1`（该目录在 .gitignore 内，不提交），仓库内不再保留。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/record_work.py tools/publish_stock.py tools/n8n_api.py scripts/watch_daily.py`；用 `rg` 找相关测试并 pytest 运行；`uv lock --check` 或 `uv sync --dry-run` 验证 lock 一致。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
