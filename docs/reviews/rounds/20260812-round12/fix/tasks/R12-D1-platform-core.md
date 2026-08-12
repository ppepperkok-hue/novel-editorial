# 修复任务包 · R12-D1 平台核心

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第十二轮审查修复（新发现 + 第十一轮遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round12/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/record_work.py`
- `tools/publish_stock.py`
- `tools/preflight.py`
- `tools/check_stock.py`

## 修复项

### R12-D1-01（P2，新）record_work.py:68-71
现状：upsert_novel 把新书合并进旧同名小说。
期望：同名书合并仅限明确意图（同 book_id 或显式参数），新书不覆盖旧书数据。

### R12-D1-02（P2，新）publish_stock.py:298-303
现状：alerts.log 写入无 OSError 保护。
期望：写入失败静默/留痕兜底，不中断发布。

### R12-D1-03（P2，新）preflight.py:54-56
现状：preflight.alert 未保护，兄弟 helper 都吞 OSError 而它不吞。
期望：与兄弟 helper 一致加 OSError 保护。

### R12-D1-04（P3，新）preflight.py:153-156
现状：acquire_lock 可因 PID 复用永久卡死（无年龄回退）。
期望：锁带时间戳年龄回退（陈旧锁可回收），PID 复用不死锁。

### R12-D1-05（P3，新）check_stock.py:37-43
现状：无活跃书时统计全库存稿，误导显示。
期望：无活跃书返回空/明确提示，不统计全库。

### R12-D1-06（L-068 后端侧）preflight.py / editorial_daily.py / control.py
现状：锁与告警日志路径仍硬编码 ROOT，未随运行时数据目录迁移。
期望：锁与告警路径改用运行时数据目录（与 config.RUNTIME_ROOT 一致）；editorial_daily/control 如不在本组文件列表，在结果中说明位置。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/record_work.py tools/publish_stock.py tools/preflight.py tools/check_stock.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
