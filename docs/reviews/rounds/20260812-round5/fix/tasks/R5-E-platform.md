# 修复任务包 · R5-E 平台工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第五轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round5/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/create_book.py`
- `tools/collect_reader_stats.py`
- `tools/record_work.py`
- `tools/preflight.py`
- `scripts/install_autostart.ps1`
- 环境修复：`.venv` 安装 `websocket-client`（R5-E-06）

## 修复项

### R5-E-01（P2）create_book.py _gender
现状：「仙侠言情」永远判为男频。
期望：按题材/关键词判断男女频，仙侠言情类应判女频或可配置。

### R5-E-02（P3）collect_reader_stats.py
现状：从环境变量读 FANQIE_BOOK_ID，与 current_book 的 DB 权威设计矛盾。
期望：以 DB 当前活跃书为准（参考 tools/current_book.py），环境变量仅兜底。

### R5-E-03（P3）record_work.py CLI
现状：硬编码 demo.db，缺少 --db 参数。
期望：补 --db 参数（默认 demo.db 或与项目一致），与其他工具一致。

### R5-E-04（P3）preflight.py
现状：--no-lock 参数声明后从未被读取。
期望：实现 --no-lock 语义（跳过锁检查/不写锁），或删除死参数（二选一，与文档一致）。

### R5-E-05（P3）install_autostart.ps1
现状：用 ASCII 写 VBS，非 ASCII 路径会被替换为 ?。
期望：改为 UTF-8 带 BOM 写 VBS（PowerShell 5.1 兼容），或避免在 VBS 中写非 ASCII 路径。

### R5-E-06（P3）环境
现状：.venv 缺 websocket-client，inject_fanqie_cookie.py 无法运行。
期望：在 `.venv` 中安装 websocket-client 并验证 `python -c import websocket` 成功；报告安装版本。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`python -m compileall tools/create_book.py tools/collect_reader_stats.py tools/record_work.py tools/preflight.py`；用 rg 找相关测试并 pytest 运行；`python -c import websocket` 验证环境。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
