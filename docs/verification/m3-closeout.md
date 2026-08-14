# M3 阶段收关报告（2026-08-14）

状态：**收关验证通过**。M1–M3 CLI 里程碑线正式收关：全量验证、真实场景、压力基线全部通过；基线数据归档，作为后续三个瓶颈优化的对照。

## 一、全量自动化（收关复跑）

| 检查 | 结果 |
| --- | --- |
| `uv run pytest` | 196 passed（60.44s） |
| `uv run ruff check .` | 0 错误 |
| `uv run pyright` | 0 错误 |
| `python scripts/verify_constitution.py` | OK |
| `uv run pytest --cov=novel_editorial` | 总覆盖率 97%；核心服务层 87%–100% |

## 二、真实场景

- `scripts/smoke_m3.py`：16 步全部 [OK]，输出 SMOKE OK（已入库可复现）。
- `scripts/stress_m3.py`：STRESS OK，独立运行两次（实现者 + 总监复跑）数值一致。

## 三、压力基线（scripts/stress_m3.py）

| 场景 | 本次运行 | 工人复跑 | 阈值 | 结果 |
| --- | --- | --- | --- | --- |
| A1 record_event 写入 10000 条 | 29.16s | 29.57s | <60s | PASS |
| A2 list_events_since 遍历 10000 条 | 0.14s | 0.14s | <10s | PASS（数量完整、rowid 严格递增） |
| A3 CLI events list --limit 20 | 1.41s | 1.43s | <5s | PASS |
| B 检索数据写入（100 版草稿 / 500 消息 / 200 意见 / 100 笔记 / 50 线索 / 20 决策） | 4.90s | 5.06s | 记录 | - |
| B1 memory search 中位 | 1435ms | 1476ms | <10s | PASS |
| B2 inspect 中位 | 1433ms | 1594ms | <10s | PASS |
| B3 inspect 无命中词 | 1.43s | 1.42s | <10s | PASS |
| C1 inspect 跨作品隔离（其余 9 个作品） | 全部 no matches | 全部 no matches | 0 串词 | PASS |
| C2 works list（10 作品） | 1.41s | 1.42s | <5s | PASS |

## 四、瓶颈量化（供优化对照）

- **瓶颈 1 CLI 单文件**：`src/novel_editorial/cli/app.py` 846 行、12 个命令组；后续扩展维护成本上升，建议按命令组拆模块（涉及目录结构，属地基变更，先评估方案再实施）。**已于 M4-ENG-1 解决**（收尾记录见 [m4-eng1-closeout.md](m4-eng1-closeout.md)）。
- **瓶颈 2 检索全表扫描**：50 万字量级下 memory search / inspect 约 1.4–1.6s，当前可用但随数据线性增长；量级再涨需索引 / FTS / 向量检索。**已于 M4-ENG-2 解决**（实测根因修正：墙钟大头是 CLI 启动导入；SQL 下沉 + 启动优化 + FTS5 trigram 索引 + 回退兜底，收尾记录见 [m4-eng2-closeout.md](m4-eng2-closeout.md)）。
- **瓶颈 3 测试耗时**：全量 pytest 60.4s（覆盖率模式 68s），随功能线性增长；CI 可分片、本地可子集。**已于 M4-ENG-3 解决**（pytest-xdist 并行 + smoke 子集 + --lf 重跑，收尾记录见 [m4-eng3-closeout.md](m4-eng3-closeout.md)）。
- **附注**：A1 写入 29s 大头在逐条 commit，事件批量写入路径可优化（后续瓶颈 2 一并评估）。

## 五、遗留与风险

- U27 图形面板（三扇窗）按计划后置。
- 真实 LLM key 端到端未验证（当前 mock 全绿）。
- 质量门阈值与词表为初版，随真实语料迭代校准。
- events watch 的 rowid 游标在引入事件删除或 VACUUM 后需重新评估。

## 六、结论

收关完成，版本 0.1.0（tag v0.1.0）。M1–M3 CLI 里程碑线完整交付；下一阶段为三个瓶颈的工程优化，随后立项自然行为与自由意志开发。
