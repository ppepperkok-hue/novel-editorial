# 第十一轮审查修复 · 轮次总结

## 1. 范围与基线

- 审查时间：2026-08-12 07:28（六片并行）
- 审查基线 commit：`2ea4b5c`（第十轮归档后）
- 修复收口 commit：（本报告提交时一并记录）
- 全量回归：`python run_tests.py` 497 passed（151s，TMP 指 E 盘）；`npx vitest run` 20 passed；`npm run build` 通过；`node tools/validate_workflow_deep.mjs` OK；`pytest --collect-only` 497 零错误
- 修复派发方式：5 组文件不相交分组，全部由独立 CLI 并行执行；本轮同时跟进第十轮遗留 5 项

## 2. 发现统计（第十一轮新发现）

| 分片 | P0 | P1 | P2 | P3 |
| --- | --- | --- | --- | --- |
| core | 0 | 0 | 1 | 1 |
| editorial | 0 | 1 | 1 | 5 |
| frontend | 0 | 0 | 3 | 3 |
| knowledge | 0 | 0 | 1 | 5 |
| platform | 0 | 0 | 1 | 4 |
| tests | 0 | 0 | 0 | 0 |
| 合计 | 0 | 1 | 7 | 18 |

## 3. 修复分组与执行

| 组 | 文件 | 项数（新+遗留） | 执行 | 验收 |
| --- | --- | --- | --- | --- |
| R11-A1 core/API | meeting_session/pipeline/web_api | 4（2+2） | CLI | 81 passed；pipeline 有旧链路引用保留 |
| R11-A2 editorial | editorial_daily/workday/export_flow_html/agent_meeting | 8（7+1） | CLI | 104 passed；compress_history 误报 |
| R11-B frontend/desktop | main.js/release.js/package.json/AgentsPage/config.py | 5（5+0） | CLI | vitest 20 + build |
| R11-C knowledge | export_agent_prompts/ai_taste/distill/novel_knowledge/knowledge_keeper | 6（5+1） | CLI | 66 passed |
| R11-D platform | create_book/preflight/publish_stock/record_work/collect_reader_stats/get_meta | 7（6+1） | CLI | 93 passed + 22 断言 |

## 4. 验证与提交

- 关键修复：create_session 并发锁、rework gate-bypass、org/meeting 并发开日、stale opening 回收、只读目录启动探测、版本自动 bump、心情归属锁定、proxy 假成功、排比启发式、per-book already_ran、翻页采集
- 收口：无测试语义冲突（497 全绿）；pipeline.py 与 compress_history 经核实为审查误报/有引用，保留
- 遗留未修项（本轮 CLI 新发现 + 留轮项，逐条保留）：
  - agent_meeting CLI 路径直接 INSERT running 会话，绕过 create_session 锁（建议统一创建入口）
  - /api/novel_knowledge upsert 错误返回 200+ok:false（与 save/accept 400 语义不一致）
  - mailroom.list_messages 的 novel_id=0 语义「不过滤」是全局消息标读问题的根源
  - daily_runs.local_executions 与 flow_graph 未映射 completed_with_pending
  - export_agent_prompts 非 proxy 全节点缺失仍 exit 0；distill lessons 元素缺 title/content 静默 continue
  - record_payload/upsert_novel 顶层形状未强制 list；get_meta bible/blueprints 错位形状原样进输出
  - collect_reader_stats 翻页依赖「短页即末页」启发式（无 total 字段）
  - control.py/editorial_daily.py/preflight.py 锁与告警路径仍硬编码 ROOT（只读安装靠启动探测拦截）
  - desktop api-error 通道 preload/webapp 未桥接；release bump 后 package-lock 根版本短暂不同步
  - 测试环境污染（n8n_tmp/t.lock）；mkdtemp 清理（L-057）
  - L-035 多文件 LF/CRLF 行尾混用（独立格式化批次）

## 5. 下一轮建议

继续开第十二轮全库分片审查；产物归档 `docs/reviews/rounds/20260812-round12/`。优先跟进：会议创建统一入口、knowledge upsert 语义统一、completed_with_pending 全链路映射、顶层形状强制、测试临时目录清理。
