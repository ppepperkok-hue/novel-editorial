# 第二轮分片审查修复记录 · 2026-08-12

来源：docs/reviews/20260812-0158-slice-*.md（汇总 0158-slices-summary.md），共 3 P1 + 6 P2 + 22 P3，无 P0。

## P1（3，提交 e295506）

| # | 分片 | 问题 | 修复 |
| --- | --- | --- | --- |
| R2-P1-1 | core | control 后台硬编码 config.DB_PATH，与面板 --db 分歧（多库/打包版双库） | control 增加 `_ACTIVE_DB`/`set_db_path`/`_db_path`，web_api 启动时把活动库传入；打包版 UI 与后台统一 userData 库 |
| R2-P1-2 | editorial | 写手分派注记在真实路径收到 envelope 而非 assignments，F1 实际未生效 | `_writer_dispatch_notes` 解包 `{mode, dispatch}` envelope；补 envelope 测试 |
| R2-P1-3 | frontend | 打包版 UI 与后台使用两个不同 SQLite 库，demo.db 未进包 | web_api `--db` 贯穿 control；desktop extraResources 补 demo.db |

## P2（6，提交 e295506）

| # | 分片 | 问题 | 修复 |
| --- | --- | --- | --- |
| R2-P2-1 | core | reminders 每 30 分钟轮询但只匹配精确分钟，可能错过提醒时间 | 改为跨分钟检测（prev_minute < target <= current 触发） |
| R2-P2-2 | editorial | produce-skipped 工作日 close 后误报 failed | workday.open 的 org 分支落 status='skipped' |
| R2-P2-3 | editorial | write_diaries dry-run 仍写日记/心情/活动日志（P1-1 泄漏面） | 三处写入全部 `if not dry_run` 短路 |
| R2-P2-4 | editorial | `_handle_outbox` 返回 JSON envelope 而非正文 | 仅剩 `{"text": ...}` 时解包返回 prose |
| R2-P2-5 | frontend | API 启动失败时桌面端静默退出 | ensureApi 失败弹 dialog 提示（不静默 quit） |
| R2-P2-6 | platform | rename_on_login.ps1 可能杀死自身进程 | 匹配时排除 `$PID` |

## P3（20 项修复，提交 642552d；2 项记录）

| # | 分片 | 问题 | 修复 |
| --- | --- | --- | --- |
| R2-P3-1 | core | knowledge_drafts distill 分支连接处理不当 | 去掉外层 conn 关闭/重连，distill_latest 自管连接 |
| R2-P3-2 | core | hot_topics.json 非原子写 | 临时文件 + os.replace |
| R2-P3-3 | core | scheduler CLI --db 相对路径未解析 | 解析到 ROOT |
| R2-P3-4 | editorial | latest_weekly/mood_of 脏 JSON 无保护 | json.loads 包 try |
| R2-P3-5 | frontend | release.js 重复执行 tag 中断 | tag 存在则跳过（幂等） |
| R2-P3-6 | frontend | CommandPalette 缺 flow/editorial 入口 | 补两条命令 |
| R2-P3-7 | frontend | WorksPage tags 直接 JSON.parse 可炸页 | try/catch 兜底 |
| R2-P3-8 | frontend | ui.jsx fmtMoney 死代码 | 删除 |
| R2-P3-9 | platform | n8n_api Set-Cookie 缺失抛 TypeError | get_all 结果 or [] |
| R2-P3-10 | platform | preflight --no-lock 参数过时 | help 标注兼容 |
| R2-P3-11 | platform | publish_stock finished 死分支 | 删除（候选查询已排除 finished） |
| R2-P3-12 | platform | inject_fanqie_cookie click_select 死代码 | 删除 |
| R2-P3-13 | platform | record_work 失败发布日志缺 created_at | INSERT 补 created_at |
| R2-P3-14 | platform | get_meta outline 脏 JSON 崩溃 | try 兜底为空 |
| R2-P3-15 | platform | check_stock 非法 pending_publish 抛 ValueError | int 转换容错 |
| R2-P3-16 | platform | delete_book 漏删 agent_messages 孤儿行 | _purge_novel 补 ref_novel_id 表清理 |
| R2-P3-17 | platform | launch_desktop.vbs 不检查 electron.exe | 加存在检查 + 提示 |
| R2-P3-18 | platform | start_n8n.ps1 硬编码 Node 路径 | Get-Command node 解析 |
| R2-P3-19 | platform | create_book/delete_book --db 相对路径未解析 | 解析到 ROOT |
| R2-P3-20 | platform | N8N_TMP_PW 等未文档化 | .env.example 补遗留 n8n 变量 |
| R2-P3-21 | legacy | n8n 遗留工作流 UTC published_at 不一致 | 记录（遗留回退路径，不修） |
| R2-P3-22 | tests | desktop 无自动化测试 | 记录（建议后续为 main.js 纯函数补最小单测） |

## 验证

后端 476 全绿（新增 4 个测试：dispatch envelope、org 收工、日记 dry-run、outbox prose），前端 16 全绿、构建通过。提交：e295506（P1/P2）、642552d（P3）。
