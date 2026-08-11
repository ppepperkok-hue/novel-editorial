# 第四轮审查修复 · 轮次总结

## 1. 范围与基线

- 审查时间：2026-08-12 03:30（六片并行，`run_review.ps1 -Scope slices`）
- 审查基线 commit：`4e87344`（第三轮归档后）
- 修复收口 commit：（本报告提交时一并记录）
- 全量回归：`python run_tests.py` 476 passed（79s，exit=0）；`npx vitest run` 16 passed；`npm run build` 通过；`node tools/validate_workflow_deep.mjs` OK
- 修复派发方式：5 组文件不相交分组，全部由独立 CLI（codex exec，deepseek-v4-flash）并行执行；连带问题 `web_api._fail_orphan_sessions` 心跳阈值由主 agent 亲自修复

## 2. 发现统计

| 分片 | P0 | P1 | P2 | P3 |
| --- | --- | --- | --- | --- |
| core | 0 | 0 | 2 | 4 |
| editorial | 0 | 0 | 0 | 0 |
| frontend | 1 | 1 | 2 | 4 |
| knowledge | 0 | 2 | 1 | 2 |
| platform | 0 | 1 | 2 | 4 |
| tests | 0 | 0 | 0 | 0 |
| 合计 | 1 | 4 | 7 | 14 |

## 3. 修复分组与执行

| 组 | 文件 | 项数 | 执行 | 验收 |
| --- | --- | --- | --- | --- |
| R4-A1 webapp | SettingsPage/AgentsPage/Shell/vite.config | 4 | CLI | vitest 16 + build |
| R4-A2 desktop | main.js/release.js | 4 | CLI | node --check |
| R4-B core | activity/meeting_session/control/n8n/backup/desktop.py | 6 | CLI | 97 passed + 全量 476 |
| R4-C knowledge | clean_novel_knowledge/novel_knowledge/knowledge_keeper/export_agent_prompts | 5 | CLI | 33 passed |
| R4-D platform | record_work/publish_stock/uv.lock/n8n_api/watch_daily/install_daily_task/finish_rename | 7 | CLI | 41 passed + uv sync 校验 |
| 连带 | web_api._fail_orphan_sessions 心跳阈值 | 1 | 主 agent | 全量回归通过 |

## 4. 验证与提交

- 关键修复抽查：P0（SettingsPage 计划任务注册失败不再静默）已由 CLI 报告 + 前端测试覆盖；P1（main.js 非 C 盘路径、clean_novel_knowledge 收敛崩溃、novel_knowledge 幂等、record_work IndexError）均有复现与行为验证记录
- 遗留清理：finish_rename.ps1、rename_on_login.ps1 归档至 `tools/archive/`（gitignore）；RunOnce 注册键确认不存在；docs/tmp_fix 清空
- 遗留未修项（CLI 报告只报未改，逐条保留）：
  - SettingsPage 的 action()/save() 无显式 catch（postJSON 已包 ok:false，风险低）
  - desktop DB 移到安装目录后，extraResources 种子库更新可能覆盖用户数据；安装目录不可写时保存设置仍会失败（根治需后端 relpath/userData 设计）
  - main.js triggerWorkflow catch 只写 console，网络失败托盘无提示
  - web_api 全量 pytest 收集会被 desktop/release 与 exports/archive 的 SystemExit 测试文件干扰（官方入口 run_tests.py 不受影响）
  - pick_port 探测与实际绑定存在 TOCTOU 窗口（既有设计）
  - export_agent_prompts END_MARK 若出现在正文内部会被提前截断
  - _merge_history keep 缺失分支仍删 drop 行及其 history（被现有测试锁死）
  - upsert_ex 对 content 相同但 change_note 非空仍 version+1
  - README 第 221 行仍列 finish_rename.ps1，归档后描述过时
  - watch_daily cost_logs 为空时 cost_today 打印 None
  - publish_stock 对 finishing + finish_remaining=0 极端数据会照单全发
  - n8n_api.py BASE 硬编码 localhost:5678；record_work.py 行尾混用 CRLF/LF

## 5. 下一轮建议

继续开第五轮全库分片审查，验证第四轮修复是否引入新问题；产物归档到 `docs/reviews/rounds/20260812-round5/`。README 遗留描述与 publish_stock 极端数据、web_api 测试收集问题建议在第五轮修复后跟进。
