# 分片审查 P1 修复评估表 · 2026-08-12

来源：首次六路并行分片审查（docs/reviews/20260812-0045-slice-*.md），共 6 个 P1、无 P0。

| # | 分片 | 问题 | 证据 | 影响 | 修复方案 | 失败测试 |
| --- | --- | --- | --- | --- | --- | --- |
| P1-1 | editorial | `--dry-run` 真实写库 | editorial_daily.py 1301/1066/1589/1531/522 | 演练污染真实数据：任务误标完成、关系被改、设置被清 | dry_run 短路：pending_publish 读写、manual_requested 清除、relations 事件、_settle_claimed_tasks 全部跳过 | dry-run 后 agent_actions/relations/settings 不变 |
| P1-2 | editorial | 旧库 schema 与代码不兼容 | relations.py:56-60 / mailroom.py:163 实测 OperationalError | 默认 demo.db（旧 schema）日更必失败 | 探测 demo.db 缺失列，补 `db._migrate` 幂等迁移 | 旧 schema 库迁移后日更链路可用 |
| P1-3 | platform | collect_reader_stats CLI 必崩 | collect_reader_stats.py:133 未定义 ENV_FILE | 阅读数据采集全挂 | 补 ENV_FILE 定义/读取路径 | CLI 冒烟跑通 |
| P1-4 | platform | delete_book 本地清除 FK 失败 | delete_book.py:43-52 IntegrityError | 番茄远程删除后本地状态永久不一致 | 按外键顺序清子表再删主行 | 删除后本地无残留 |
| P1-5 | knowledge | 章节摘要重复同步致 version/history 无限膨胀 | novel_knowledge.py:195-208 | 知识库无限增长、检索变慢 | 同内容不重复写版本（内容哈希或最新同内容跳过） | 重复同步不新增行 |
| P1-6 | frontend | release.js 永远无法发版 | desktop/release.js gh release view 抛错中止 | 桌面壳无法自动更新发布 | release 不存在时容错（检查 exit code 而非抛错） | 无 release 时脚本继续 |

修复顺序：P1-1 → P1-2 → P1-3 → P1-4 → P1-5 → P1-6。每项先写失败测试，修完跑 `python run_tests.py` 全量回归（448 基线），提交推送；修复记录追加到本表。

## 修复记录

| # | 状态 | 提交 | 说明 |
| --- | --- | --- | --- |
| P1-1 | ✅ | 38c273c | dry-run 短路：pending_publish/manual_requested/relations 事件/_settle_claimed_tasks 全跳过；新增 `_rel` helper；失败测试 test_dry_run_has_no_db_side_effects |
| P1-2 | ✅ | 9f77f3f | db._migrate 补 `agent_relations.other`（含 other_agent 数据迁移）与 `agent_messages.resolution`；demo.db 实库迁移验证；失败测试 test_legacy_schema_migrates_relations_and_messages |
| P1-3 | ✅ | 8649492 | collect_reader_stats `--env-file` 默认值改用 `config.N8N_ENV_FILE`；失败测试 CLI --help 冒烟（stdout 重定向防污染） |
| P1-4 | ✅ | 8649492 | `_purge_novel` 三阶段删除：chapter_id 子表 → chapters/volumes → 其余 novel_id 表 → novels；失败测试 test_purge_novel_is_fk_safe |
| P1-5 | ✅ | f4c7361 | upsert 幂等：内容相同且无 change_note 时跳过版本/历史写入；合并事件仍版本化；失败测试 test_upsert_same_content_is_idempotent |
| P1-6 | ✅ | 待提交 | release.js 对 `gh release view` 不存在容错；顺带清理 desktop 产物名与发版文案残留的 pipeline 命名；`node --check` 验证 |

全量回归：453 后端 + 16 前端全绿（P1-1 后 449 → P1-2 后 450 → P1-3/P1-4 后 452 → P1-5 后 453）。
