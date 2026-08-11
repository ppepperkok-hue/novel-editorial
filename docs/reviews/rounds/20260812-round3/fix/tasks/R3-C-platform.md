# 修复任务包 · R3-C 平台发布与 CLI

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第三轮分片审查修复，审查报告原文：`docs/reviews/20260812-0225-slices-summary.md`（可读确认细节）。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/publish_stock.py`
- `tools/preflight.py`
- `tools/collect_reader_stats.py`
- `tools/get_meta.py`
- `tools/record_work.py`
- `launch_desktop.vbs`

## 修复项

### R3-C-01（P2）publish_stock.py:335-341
现状：CLI 在多书并存时选中最小 novel_id 而非活跃书。
期望：按活跃书语义选择（参考 tools/current_book.py 或同文件其他逻辑）；无活跃书时明确报错/提示，不静默选最小 id。

### R3-C-02（P3）publish_stock.py:356-358
现状：对 pending_publish/daily_chapters 的 int() 无容错，脏配置直接崩溃。
期望：解析失败用默认值并留痕，或返回带明确错误的结构，不整体崩溃。

### R3-C-03（P3）preflight.py:38-40
现状：--env-file 参数是空操作（load_env 忽略入参）。
期望：让 load_env 真正接受并加载指定的 env 文件；不传时行为不变。

### R3-C-04（P3）collect_reader_stats.py:28-30
现状：--env-file 参数是空操作（load_env 忽略入参）。
期望：同上，让 load_env 真正接受并加载指定的 env 文件；不传时行为不变。

### R3-C-05（P3）get_meta.py:104-106
现状：多处 json.loads 无保护，脏 JSON 使 CLI 整体崩溃。
期望：解析失败返回默认值/空结构并留痕，不整体崩溃。

### R3-C-06（P3）record_work.py:230
现状：对 expected_recover 的 int() 无容错，LLM 脏数据使整次记录崩溃。
期望：解析失败用默认值并留痕，不中断记录。

### R3-C-07（P3）launch_desktop.vbs:6-7
现状：无 BOM UTF-8 中文提示被 cscript 按 ANSI 解码成乱码。
期望：给 vbs 保存为带 BOM 的 UTF-8（保持 .vbs 语法合法），或改用纯 ASCII 英文提示，确保 cscript 下不乱码。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：
  - `python -m compileall tools/publish_stock.py tools/preflight.py tools/collect_reader_stats.py tools/get_meta.py tools/record_work.py`
  - 用 `rg` 找 tests 中引用 publish_stock/preflight/collect_reader_stats/get_meta/record_work 的测试，`python -m pytest <相关测试文件> -q` 运行。
  - vbs 改动用 `cscript //nologo launch_desktop.vbs` 不能实跑（会启动桌面端），改为人工核对编码与语法。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
