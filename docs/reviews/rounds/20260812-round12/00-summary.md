# 第十二轮审查修复 · 轮次总结

## 1. 范围与基线

- 审查时间：2026-08-12 07:53（六片并行）
- 审查基线 commit：`ed02196`（第十一轮归档后）
- 修复收口 commit：（本报告提交时一并记录）
- 全量回归：`python run_tests.py` 504 passed（152s，TMP 指 E 盘）；`npx vitest run` 20 passed；`npm run build` 通过；`node tools/validate_workflow_deep.mjs` OK；`pytest --collect-only` 502 零错误
- 修复派发方式：7 组文件不相交分组，全部由独立 CLI 并行执行；本轮同时跟进第十一轮遗留 4 项
- 用户约定：本轮存在 2 个 P1（并发 history 污染、链式合并丢内容），按约定继续修复不停

## 2. 发现统计（第十二轮新发现）

| 分片 | P0 | P1 | P2 | P3 |
| --- | --- | --- | --- | --- |
| core | 0 | 0 | 0 | 0 |
| editorial | 0 | 0 | 2 | 4 |
| frontend | 0 | 0 | 1 | 3 |
| knowledge | 0 | 2 | 1 | 4 |
| platform | 0 | 0 | 3 | 5 |
| tests | 0 | 0 | 0 | 2 |
| 合计 | 0 | 2 | 7 | 18 |

## 3. 修复分组与执行

| 组 | 文件 | 项数（新+遗留） | 执行 | 验收 |
| --- | --- | --- | --- | --- |
| R12-A1 core/API | daily_runs/web_api | 2（1+1） | CLI | 26 passed + 复现 |
| R12-A2 editorial | editorial_daily/agent_meeting | 5（4+1） | CLI | 95 passed（2 旧断言收口更新） |
| R12-B frontend/desktop | main.js/release.js/CommandPalette | 4（3+1） | CLI | vitest 20 + build |
| R12-C knowledge | novel_knowledge/clean_novel_knowledge/distill/knowledge_keeper/export | 7（6+1） | CLI | 30 passed + 并发 20 轮 |
| R12-D1 platform 核心 | record_work/publish_stock/preflight/check_stock | 6（5+1） | CLI | 105 passed + 6 断言 |
| R12-D2 platform 工具 | create_book/n8n_api/inject_fanqie_cookie/start_n8n | 3（3+0） | CLI | 47 passed + 4 场景 |
| R12-E tests/config | .env.example/run_tests/test_apply_architect | 3（2+1） | CLI | 契约守护 + 5 新单测 |
| 收口 | test_agent_meeting dry-run 断言 + test_editorial_daily 摩擦方向 | — | 主 agent | 504 passed |

## 4. 验证与提交

- 关键修复：upsert_ex 并发 history 原子化（P1）、链式合并并查集（P1）、review tone 方向、dry-run 全链无落库、create_session 统一入口、同名书合并语义、锁年龄回退、create_book 幂等恢复
- 收口测试更新：meeting dry-run 断言 0 行；摩擦方向插入改为 reviewer→writer
- 遗留未修项（本轮 CLI 新发现 + 留轮项，逐条保留）：
  - merge_blueprints 无 seq 更新重复应用不断新增（幂等只对带 seq 成立）
  - editorial_daily.py:562/1681/1748、control.py:242、autopilot.py:30 仍 ROOT 硬编码锁/临时/备份路径（部分已迁移）
  - create_session 跨进程 TOCTOU（进程内锁不足，需唯一约束/条件 INSERT）
  - CLI no-novel 分支退出码 0 与 create_session 失败 1 不一致；CLI round_speech 不传 compressed_history
  - upsert 空 entity/content 仍 200+ok:false；同步失败运行每次重调 _execution_failure 覆盖已有失败详情
  - create_book 按完整书名去重（同名旧书删库后恢复可能绑错）；书单最多 400 本
  - 测试共用 ROOT/n8n_tmp/t.lock 顺序敏感互踩；mkdtemp 清理（L-057）
  - export 非 proxy 全节点缺失 exit 0；distill 元素缺字段静默 continue
  - L-035 多文件 LF/CRLF 行尾混用（独立格式化批次）

## 5. 下一轮建议

继续开第十三轮全库分片审查；产物归档 `docs/reviews/rounds/20260812-round13/`。优先跟进：merge_blueprints 无 seq 幂等、跨进程会话锁、ROOT 硬编码路径收尾、测试锁目录隔离。
