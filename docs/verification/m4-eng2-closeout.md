# M4-ENG-2 收尾记录（瓶颈 2：检索性能）

状态：**完成**。检索性能瓶颈解决，审查链全部闭合，新基线归档。

## 背景

m3-closeout.md 记录瓶颈 2：50 万字量级下 memory search / inspect 约 1.4s（阈值 <10s）。

## 实测根因（M4-ENG-2-A 完成后修正）

检索函数本体只占 5~15ms；CLI 墙钟 ~1.4s 的大头是启动导入链（openai ~0.9s + alembic ~0.5s）。因此方案 A（SQL 下沉）只解决函数级，方案 A2（启动导入优化）才是墙钟 <1s 的关键；方案 B（FTS5）收益主要在更大数据量与进程常驻场景。

## 实施

- `c4d7f6c`（A）：检索下沉 SQL LIKE 过滤 + 命中行按需加载；% _ \ 转义保持子串语义；新旧输出 8 组逐字节一致。
- `6f7bf7f`（A2）：openai/alembic 延迟导入 + CLI 命令组惰性注册；守卫测试防重依赖回爬启动链。
- `8b0541c`（B）：FTS5 trigram 影子表迁移（五层 + 15 触发器 + 幂等回填）；3 字符及以上走 FTS、2 字符回退 LIKE。
- `ff95a36`→`9cdc194`（BFIX 链）：子查询 JOIN + LIKE 精筛（双路径一致、消除变量上限）；运行时探测（真实试建，覆盖可加载扩展/trigram 缺失）；影子表缺失回退；残留自愈；清理失败 stderr 警告。

## 验证与基线

- 全量测试：259 passed（含 test_fts.py 17 项守卫）。
- ruff / pyright / 宪法：全绿。
- 真实场景冒烟：SMOKE OK。
- 压力基线（50 万字量级，脚本 scripts/stress_m3.py）：

| 指标 | M3 基线 | M4-ENG-2 后 |
| --- | --- | --- |
| memory search CLI 墙钟（中位） | ~1.4s | ~0.72-0.76s |
| inspect CLI 墙钟（中位） | ~1.4s | ~0.72-0.74s |
| version CLI 墙钟 | ~1.4s | ~0.18-0.23s |
| import cli.app | ~1.22s | ~0.09s |
| 事件写入 10000 条 | 29.44s | 28.8-29.4s（阈值 <60s） |
| 多作品隔离 | 无串词 | 无串词 |

- 函数级对比（in-process）：高频命中 LIKE/FTS 相当（命中行渲染占大头）；罕见命中/无命中 FTS 快 1.4-2.3x。

## 审查链

- 初始审查（8b0541c）：2 P2 + 1 P3，全部修复；修复链 6 轮收敛至 Ready to merge。
- 报告归档：docs/reviews/20260814-M4-ENG2-initial.md、docs/reviews/20260814-M4-ENG2-fix.md。

## 结论

瓶颈 2 收口。检索 CLI 墙钟较基线改善约 50%，函数级具备 FTS 索引（3 字符以上走索引），无 FTS5 环境自动回退 LIKE。下一瓶颈：测试分片/本地子集（M4-ENG-3）。
