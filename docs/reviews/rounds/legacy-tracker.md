# 跨轮次遗留跟踪表

> 规则：每轮收口时更新状态。状态 = 待处理 / 已修 / 不处理（附原因）。下一轮任务包必须显式登记或处理每一项「待处理」。

| 编号 | 来源 | 遗留项 | 文件 | 状态 |
| --- | --- | --- | --- | --- |
| L-001 | R3 | agent_save I/O 异常未捕获、回滚只覆盖 returncode 分支 | agents.py | 已修（R7-A2-01） |
| L-002 | R3 | claim_task 拒绝原因未进 audit detail | agency.py | 已修（R7-A2-02） |
| L-003 | R3 | start_topic_meeting 默认参数 demo.db（无调用方） | misc.py | 已修（R7-A1-07） |
| L-004 | R3 | do_POST 非法 JSON body 仍 500；create 的 novel_id 未整数清洗 | web_api.py | 已修（R7-A1-06） |
| L-005 | R3 | seed_demo 对负数参数无校验 | seed_demo.py | 已修（R7-A2-03） |
| L-006 | R3 | _preflight dry-run 下仍写 audit_logs | editorial_daily.py | 已修（R7-B1-03） |
| L-007 | R3 | tags 裸 json.loads、settings int() 无兜底 | architect_weekly.py | 已修（R7-B1-06） |
| L-008 | R3 | meeting_actions config 死导入 | meeting_actions.py | 已修（R7-B2-06） |
| L-009 | R3 | agent_meeting ask 内重复 import knowledge | agent_meeting.py | 已修（R7-B2-05） |
| L-010 | R3 | export_flow_html JS 端 STATUS 无白名单 | export_flow_html.py | 已修（R7-B2-08） |
| L-011 | R3 | ai_taste_check detect 明细 map 逐词重叠计数 | ai_taste_check.py | 已修（R7-B1-07） |
| L-012 | R3 | 打包版计划任务依赖 PATH 上的 python | install_daily_task.ps1 / main.js | 已修（R7-C1-07 Resolve-PythonExe） |
| L-013 | R4 | SettingsPage action()/save() 无显式 catch（postJSON 已包 ok:false） | SettingsPage.jsx | 已修（R7-C2-05） |
| L-014 | R4 | main.js triggerWorkflow catch 只写 console，托盘无提示 | main.js | 已修（R7-C1-04） |
| L-015 | R4 | web_api 全量 pytest 收集被 SystemExit 测试文件干扰 | 测试卫生 | 已修（R7-E-06 + 根 conftest） |
| L-016 | R4 | pick_port 探测与绑定 TOCTOU | desktop.py | 不处理（既有设计，低风险） |
| L-017 | R4 | export_agent_prompts END_MARK 正文内提前截断 | export_agent_prompts.py | 已修（R7-D-05） |
| L-018 | R4 | _merge_history keep 缺失删 drop 行及 history | clean_novel_knowledge.py | 不处理（被现有测试锁定的设计契约） |
| L-019 | R4 | upsert_ex content 相同但 change_note 非空仍 version+1 | novel_knowledge.py | 已修（R7-D-01 + 测试断言更新） |
| L-020 | R4 | README 仍列 finish_rename.ps1（归档后过时） | README.md | 已修（R7-E-04） |
| L-021 | R4 | watch_daily cost_logs 空时 cost_today 打印 None | watch_daily.py | 已修（R7-E-02） |
| L-022 | R4 | publish_stock finishing + finish_remaining=0 极端数据照单全发 | publish_stock.py | 已修（R7-E-01） |
| L-023 | R5 | ending.py Path 死导入 | ending.py | 已修（R7-E-03） |
| L-024 | R5 | workday.main() 业务失败 CLI 仍 exit 0 | workday.py | 已修（R7-B1-05） |
| L-025 | R5 | meeting_actions audit 自提交，重试可能重复写审计行 | meeting_actions.py | 已修（R7-B2-07） |
| L-026 | R5 | 草稿书隔离靠 title 前缀，长期应加 novel_id 列 | novel_knowledge.py | 已修（R7-D-02 幂等迁移） |
| L-027 | R5 | main.js pythonw spawn 失败白等 20 秒 | main.js | 已修（R7-C1-05） |
| L-028 | R5 | README 仍列 MONTHLY_BUDGET 等死键 | README.md / n8n/README.md | 已修（R7-E-05） |
| L-029 | R6 | _run_locked 会话行不存在仍静默 return | meeting_session.py | 已修（R7-A2-04） |
| L-030 | R6 | _review_tone 等查询硬编码 other=?（旧迁移数据漏匹配） | editorial_daily.py | 已修（R7-B1-04） |
| L-031 | R6 | main.js 30 秒轮询无超时/重入保护 | main.js | 已修（R7-C1-06） |
| L-032 | R6 | App.jsx usePolling error 不再被消费（冗余） | App.jsx | 已修（R7-C2-04） |
| L-033 | R6 | sync_latest 两路径结构差 count 键 | novel_knowledge.py | 已修（R7-D-03） |
| L-034 | R6 | _add_conflict_draft 的 category 参数未使用 | novel_knowledge.py | 已修（R7-D-04） |
| L-035 | R6 | 多文件 LF/CRLF 行尾混用 | 批量 | 待处理（独立格式化批次，避免混 diff） |
| L-036 | R6 | config.load_env 只 strip 不剥行内注释 | config.py | 已修（R7-A1-08） |
| L-037 | R5 | bind_book env 写成功后 DB 提交异常的小概率半更新 | ending.py | 不处理（小概率，方向已修正） |
| L-038 | R5 | _normalize_action_items 不含全角逗号 | activity.py | 不处理（既有行为） |
| L-039 | R4 | run_session 省略 db_path 无法定位行内库（设计上限） | meeting_session.py | 已修（R6-A-02 显式报错） |
| L-040 | R4 | n8n_api BASE 硬编码 localhost:5678 | n8n_api.py | 已修（R6-E-05） |
| L-041 | R5 | world_events dict 静默丢弃 | novel_knowledge.py | 已修（R6-D-02） |
| L-042 | R5 | sync_latest 缺 skipped 键 | novel_knowledge.py | 已修（R6-D-01） |
| L-043 | R5 | quality_gate ai_words.json 损坏静默 | quality_gate.py | 已修（R6-F-02） |
| L-044 | R5 | compliance_words.txt 全注释 EMPTY 警告 | compliance_words.txt | 已修（R6-F-06 填词） |
| L-045 | R4 | desktop 种子库升级覆盖用户数据 | main.js | 已修（R5-C-02 userData 隔离） |
| L-046 | R3 | quality_gate ai_flavor isinstance 校验 | quality_gate.py | 已修（R5-F-01） |
| L-047 | R3 | N8N 死配置 / REVIEW_RETRY_MAX 文档 | .env.example | 已修（R5-F-04 / R6-F） |
