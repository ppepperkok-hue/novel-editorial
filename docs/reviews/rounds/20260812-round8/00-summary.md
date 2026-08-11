# 第八轮审查修复 · 轮次总结

## 1. 范围与基线

- 审查时间：2026-08-12 05:27（六片并行）
- 审查基线 commit：`53065f3`（第七轮归档后）
- 修复收口 commit：（本报告提交时一并记录）
- 全量回归：`python run_tests.py` 487 passed（152s，TMP 指 E 盘）；`npx vitest run` 17 passed；`npm run build` 通过；`node tools/validate_workflow_deep.mjs` OK；`pytest --collect-only` 487 零错误
- 修复派发方式：7 组文件不相交分组，全部由独立 CLI 并行执行；本轮同时跟进第七轮遗留 13 项

## 2. 发现统计（第八轮新发现）

| 分片 | P0 | P1 | P2 | P3 |
| --- | --- | --- | --- | --- |
| core | 0 | 0 | 0 | 2 |
| editorial | 0 | 0 | 2 | 3 |
| frontend | 0 | 0 | 0 | 0 |
| knowledge | 0 | 1 | 3 | 1 |
| platform | 0 | 1 | 2 | 3 |
| tests | 0 | 0 | 0 | 4 |
| 合计 | 0 | 2 | 7 | 13 |

## 3. 修复分组与执行

| 组 | 文件 | 项数（新+遗留） | 执行 | 验收 |
| --- | --- | --- | --- | --- |
| R8-A1 core/API | web_api/meeting_session/agency | 6（1+5） | CLI | 143 passed + 17 点行为验证 |
| R8-A2 webapp | ExecutionsPage/dashboard.test | 2（2+0） | CLI | vitest 17 + build |
| R8-B1 editorial | agent_meeting/editorial_daily/mailroom/write_diaries/architect_weekly/workday | 7（5+2） | CLI | 127 passed + 全量；1 项留轮（唯一索引） |
| R8-B2 链路展示 | export_flow_html/flow_graph | 1（0+1） | CLI | 8 passed；逐节点状态口径 |
| R8-C knowledge | novel_knowledge/knowledge_keeper/distill_lessons/clean_novel_knowledge/ai_taste | 5（5+0） | CLI | 29 passed |
| R8-D platform | get_meta/record_work/check_stock/preflight/publish_stock | 6（6+0） | CLI | 487 全量 + 6 项复现 |
| R8-E tests/config | README/run_tests/ai_words/package.json/.env.example | 5（3+2） | CLI | 487 全量 + FileMatcher 验证 |

## 4. 验证与提交

- 关键修复：planning 会话根因（create_session 不绑书 + _run_locked 不 apply_report）、run_session 异常落盘、知识库 WAL 备份完整性、record_work 同 run_id 幂等、publish/preflight 运行锁、逐节点失败链路图
- 收口：无测试语义冲突需更新（487 全绿）；清理 desktop/release 旧构建残留已于第七轮完成
- 遗留未修项（本轮 CLI 新发现 + 留轮项，逐条保留）：
  - run_post_actions 并发窗口需唯一索引根治（B1-06 留轮，meeting_actions.py/audit_logs）
  - FlowPage.jsx 未消费 node_status（链路图前端仍全红）
  - FAILED_ALIAS 未映射 legacy n8n 名字；预检失败不写 failed_nodes
  - _parse_json 用首尾花括号截取，LLM 值含花括号会截错（novel_knowledge/knowledge_keeper）
  - clean_novel_knowledge 备份文件名只精确到秒，同秒重跑互相覆盖
  - knowledge_keeper 读热点 JSON 为 list 时 hot.get 崩溃
  - record_work.py:300 seq 裸 int 转换
  - preflight 顶层 LOCK_FILE 常量（daily.lock）与实际 {db stem}.lock 不一致
  - 测试普遍不清理 mkdtemp 目录（C 盘六万临时目录残留隐患）
  - ExecutionsPage fmt 死代码、colSpan=7 vs 6 列、toggleRun 失败无提示
  - ending.py 仍写 FANQIE_VOLUME_ID（模板已弃用，死写）
  - editorial_steps DEFAULT_FLAVOR_WORDS 无权威来源标注（与 quality_gate 同族漂移）
  - workday.close ok 语义变化后需检查面板消费方
  - L-035 多文件 LF/CRLF 行尾混用（独立格式化批次）

## 5. 下一轮建议

继续开第九轮全库分片审查；产物归档 `docs/reviews/rounds/20260812-round9/`。优先跟进：run_post_actions 唯一索引、FlowPage node_status 消费、_parse_json 截取边界、测试临时目录清理（mkdtemp 泄漏与 C 盘空间）。
