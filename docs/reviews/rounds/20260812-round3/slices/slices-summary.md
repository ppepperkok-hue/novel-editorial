# 分片审查汇总 · 20260812-0225

## core

### P1（1）
- [P1] agency._dispatch 对畸形 action_id 无类型防护，ValueError 中断整批动作并击穿日更链路 — E:\code\novel-editorial\novel_editorial\services\agency.py:60-98

### P2（2）
- [P2] agent_save 在渲染/校验失败时仍返回 ok=True，造成假绿灯 — E:\code\novel-editorial\novel_editorial\services\agents.py:139-144
- [P2] apply_schedule 硬编码 demo.db，与 --db 参数及手动触发路径不一致 — E:\code\novel-editorial\novel_editorial\services\control.py:289-290

### P3（8）
- [P3] monitor.run_checks 部分凭据场景不加载 .env 导致误报 Cookie/CSRF 缺失 — E:\code\novel-editorial\novel_editorial\monitor.py:36-42
- [P3] Scheduler.tick 未注入时钟时 date 字段为字符串 "None" — E:\code\novel-editorial\novel_editorial\scheduler.py:46-46
- [P3] seed_demo.seed 在 published+reviewed 超过 chapters 时产生负数 draft 导致状态错位 — E:\code\novel-editorial\novel_editorial\seed_demo.py:21-26
- [P3] update_draft_status 对 reject/deprecate 也写入 accepted_at — E:\code\novel-editorial\novel_editorial\services\knowledge.py:224-228
- [P3] web_api do_POST 对垃圾 Content-Length 头抛 500 而非 400 — E:\code\novel-editorial\novel_editorial\web_api.py:645-647
- [P3] /api/agent_actions/create 的 session_id/meeting_id 未做整数清洗，非数字 payload 返回 500 — E:\code\novel-editorial\novel_editorial\web_api.py:731-739
- [P3] load_hot_topics 对损坏的 hot_topics.json 无兜底，拖垮 /api/dashboard — E:\code\novel-editorial\novel_editorial\services\misc.py:36-42
- [P3] agents._extract_node_system 为无调用方的死代码 — E:\code\novel-editorial\novel_editorial\services\agents.py:39-45

## editorial

### P2（1）
- [P2] dry-run 收工/续工仍写入状态机，会真实关闭工作日或阻塞后续 open — E:/code/novel-editorial/tools/workday.py:306-309

### P3（9）
- [P3] flow 报告把 daily_runs.status 未转义插入 HTML class 属性 — E:/code/novel-editorial/tools/export_flow_html.py:125-125
- [P3] export_flow_html 中 groups 变量为死代码 — E:/code/novel-editorial/tools/export_flow_html.py:81-83
- [P3] rework_applied 全局标志导致第二个重做请求被静默丢弃且行动项悬置 — E:/code/novel-editorial/tools/editorial_daily.py:1160-1167
- [P3] relations.decay 的 days 参数从未使用 — E:/code/novel-editorial/tools/relations.py:85-88
- [P3] meeting_actions 幂等标记检查与插入非原子，并发可重复应用 — E:/code/novel-editorial/tools/meeting_actions.py:33-38
- [P3] 发布链 cover_article 响应未检查，失败静默继续发布 — E:/code/novel-editorial/tools/editorial_daily.py:1245-1245
- [P3] 主编分派与重写轮中的 mailroom 调用未检查返回值 — E:/code/novel-editorial/tools/editorial_daily.py:621-626
- [P3] agent_meeting.ask 工具循环 final round 无重试，单次网络抖动会中断整场会议 — E:/code/novel-editorial/tools/agent_meeting.py:252-263
- [P3] 周会材料/落盘对 novels.outline 的 JSON 解析无异常保护 — E:/code/novel-editorial/tools/architect_weekly.py:181-181

## frontend

### P1（1）
- [P1] dialog.showErrorBox 使用了未导入的 dialog，启动失败路径必然抛 ReferenceError — E:\code\novel-editorial\desktop\main.js:221-221

### P2（3）
- [P2] AgentsPage 心情面板读写使用不同 agent key，保存后永远无法回显 — E:\code\novel-editorial\webapp\src\components\AgentsPage.jsx:127-137
- [P2] WorksPage 手动绑定书请求失败时按钮永久卡在“绑定中” — E:\code\novel-editorial\webapp\src\components\WorksPage.jsx:352-357
- [P2] 桌面打包版保存每日时间后，计划任务指向资源目录种子库且脚本未打包 — E:\code\novel-editorial\desktop\package.json:31-41

### P3（3）
- [P3] 多处按钮直接 await postJSON 无 catch，后端离线时静默失败且无提示 — E:\code\novel-editorial\webapp\src\api.js:10-16
- [P3] 后端离线时 App 永久显示骨架屏，连接错误提示不可见 — E:\code\novel-editorial\webapp\src\App.jsx:139-141
- [P3] FlowPage 重复定义 API_BASE，属死代码 — E:\code\novel-editorial\webapp\src\components\FlowPage.jsx:6-8

## knowledge

（本分片无显式 P0-P3 条目）

## platform

### P1（2）
- [P1] inject_fanqie_cookie.py 顶层残留缩进块导致 IndentationError，脚本完全无法运行 — E:\code\novel-editorial\scripts\inject_fanqie_cookie.py:94-105
- [P1] delete_book._purge_novel 漏删 novel_knowledge_history，FK 违例使清除失败并留下孤儿数据 — E:\code\novel-editorial\tools\delete_book.py:64-78

### P2（1）
- [P2] publish_stock CLI 在多书并存时选中最小 novel_id 而非活跃书 — E:\code\novel-editorial\tools\publish_stock.py:335-341

### P3（6）
- [P3] publish_stock 对 pending_publish/daily_chapters 的 int() 无容错，脏配置直接崩溃 — E:\code\novel-editorial\tools\publish_stock.py:356-358
- [P3] preflight.py --env-file 参数是空操作（load_env 忽略入参） — E:\code\novel-editorial\tools\preflight.py:38-40
- [P3] collect_reader_stats.py --env-file 参数是空操作（load_env 忽略入参） — E:\code\novel-editorial\tools\collect_reader_stats.py:28-30
- [P3] get_meta.py 多处 json.loads 无保护，脏 JSON 使 CLI 整体崩溃 — E:\code\novel-editorial\tools\get_meta.py:104-106
- [P3] record_work 对 expected_recover 的 int() 无容错，LLM 脏数据使整次记录崩溃 — E:\code\novel-editorial\tools\record_work.py:230-230
- [P3] launch_desktop.vbs 无 BOM UTF-8 中文提示会被 cscript 按 ANSI 解码成乱码 — E:\code\novel-editorial\launch_desktop.vbs:6-7

## tests

### P2（1）
- F1 | P2 | novel_editorial/quality_gate.py:50 | style 分低估，AI 味密度虚高最多 2 倍；与另两个消费方计数不一致 | 文本含"缓缓说道/微微一愣"且走 score_chapter |

### P3（5）
- F2 | P3 | tools/ai_taste_check.py:48-53 | 修复无回归保护，词表变更会静默改变密度 | 未来修改 FLOWERY/FILLER |
- F3 | P3 | .env.example:34-35,58-59 | 重复键 + setdefault 先值生效，改后一组被静默忽略 | 用户只编辑 58-59 行 |
- F4 | P3 | .env.example | MEETING_MODE、N8N_*、AGENT_CTX_* 无文档 | 新环境配置时 |
- F5 | P3 | compliance_words.txt | 空词库无告警、真实文件无测试覆盖 | 发布前合规扫描依赖自定义词时 |
- F6 | P3 | 仓库根 _repro_*.py、docs/reviews/*.err | 误提交风险、读真实库 | 任何一次 git add . |

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 4 |
| P2 | 8 |
| P3 | 31 |
