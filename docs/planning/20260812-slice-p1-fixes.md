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

## P2 修复登记表（2026-08-12 追加）

| # | 分片 | 问题 | 位置 | 状态 |
| --- | --- | --- | --- | --- |
| P2-1 | core | `run_workflow_now("daily")` 假启动（返回成功未启动任务） | control.py:216-223 | ✅ 54a5d0e |
| P2-2 | core | `_run_cli` 吞掉非零退出码，周会链路静默失败 | control.py:85-97 | ✅ 54a5d0e |
| P2-3 | core | 畸形 agency/outbox 字段使会议崩溃 | meeting_session.py:294-295 | ✅ 54a5d0e |
| P2-4 | editorial | `_unwrap_text` 剥离 outbox/agency 字段致协作静默丢失 | agent_tool_loop.py:140-153 | ✅ 54a5d0e |
| P2-5 | editorial | `auto_fill_actions --days` 参数无效 | auto_fill_actions.py:46-48 | ✅ 54a5d0e |
| P2-6 | platform | delete_book 未处理 URLError/HTTPError 崩溃 | delete_book.py:83-87 | ✅ 71da4b4 |
| P2-7 | platform | preflight 锁记录退出中进程的 PID，锁可被偷 | preflight.py:122-126 | ✅ 71da4b4 |
| P2-8 | platform | record_work 摘要为纯字符串时崩溃 | record_work.py:222 | ✅ 71da4b4 |
| P2-9 | platform | pending_publish 发布前被清，失败时请求静默丢失 | publish_stock.py:363-367 | ✅ 71da4b4 |
| P2-10 | platform | websocket-client 未声明依赖 | pyproject.toml:10 | ✅ 71da4b4 |
| P2-11 | knowledge | clean 删除带 history 的行触发外键崩溃 | clean_novel_knowledge.py:209-214 | ✅ 99609a7 |
| P2-12 | knowledge | 链式合并引用已删除行，`--apply` 崩溃 | clean_novel_knowledge.py:127-141 | ✅ 99609a7 |
| P2-13 | knowledge | 模型非 JSON 输出时知识管家静默成功（假绿） | knowledge_keeper.py:135-160 | ✅ 99609a7 |
| P2-14 | knowledge | 知识包更新后 frontmatter updated_at 不刷新 | knowledge_keeper.py:176 | ✅ 99609a7 |
| P2-15 | frontend | AgentsPage 传 `.md` 后缀 key 致日记/心情接口失效 | AgentsPage.jsx | ✅ b55f690 |
| P2-16 | frontend | WorksPage 新书创意面板读不存在的接口字段 | WorksPage.jsx | ✅ b55f690 |

全量回归：465 后端 + 16 前端全绿（新增 12 个 P2 失败测试转绿）。六个分片报告（docs/reviews/20260812-0045-slice-*.md）与汇总索引（*-slices-index.md）为归档来源。

## P3 修复登记表（2026-08-12 追加）

| # | 分片 | 问题 | 位置 | 状态 |
| --- | --- | --- | --- | --- |
| P3-1 | core | `_serve_static` 前缀检查可逃逸到 dist 兄弟目录 | web_api.py:1021-1028 | ✅ 97d33ca |
| P3-2 | core | claim_action check-then-act 竞态致重复认领 | activity.py:132-144 | ✅ 97d33ca |
| P3-3 | editorial | `_mark_injected_read` 把自己发的消息标已读 | editorial_daily.py:107-117 | ✅ 97d33ca |
| P3-4 | editorial | round_speech 的 `if tool_calls:` 分支死代码 | agent_meeting.py:431-486 | ✅ 97d33ca |
| P3-5 | editorial | weekly_payload 历史日记 json.loads 无保护 | write_diaries.py:118-120 | ✅ 97d33ca |
| P3-6 | platform | check_stock `--novel-id` 未接 CLI | check_stock.py:88 | ✅ 7285138 |
| P3-7 | knowledge | ai_taste_check 漏检全角问号连续/叹问组合 | ai_taste_check.py:34 | ✅ 7285138 |
| P3-8 | knowledge | novel_knowledge 死参数与 CLI 文档不一致 | novel_knowledge.py:365 | ✅ 7285138 |
| P3-9 | knowledge | prompts/ 根目录旧模板死文件 | prompts/editor.md 等 | ✅ 7285138（并修后备管线路径指向 prompts/agents） |
| P3-10 | knowledge | export_agent_prompts 导出丢失 max_tokens | export_agent_prompts.py:72-76 | ✅ 7285138 |
| P3-11 | knowledge | distill_lessons 脏 JSON 无保护 | distill_lessons.py:83-89 | ✅ 7285138 |
| P3-12 | frontend | DashboardPage 发布章数 modal/runNow 死代码 | DashboardPage.jsx | ✅ 2aae15c（章数选择并入开工卡片） |
| P3-13 | frontend | desktop/main.js 注册未暴露的 IPC | desktop/main.js | ✅ 2aae15c |
| P3-14 | frontend | desktop/main.js spawn pythonw 无错误处理 | desktop/main.js | ✅ 2aae15c（error 事件 + api-error 通道） |
| P3-15 | tests | run_tests.py 零测试假绿 + ai_words 重叠双倍计数 + .env.example 遗漏 + 午夜边界 flake | tests/run_tests.py 等 | ✅ 2aae15c + dae8334（零测试守卫、非重叠计数、env 补全、due-date 断言跨天容差） |

全量回归：472 后端 + 16 前端全绿（P3-15 的午夜边界 flake 已通过跨天容差断言修复）。

流程约定：每次分片审查完成后，`run_review.ps1` 自动调用 `tools/summarize_slices.py` 生成 `*-slices-summary.md`（多份报告先汇总），再归档索引、汇总与各分片报告。
