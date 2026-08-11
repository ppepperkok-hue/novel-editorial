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

## 第九轮新增遗留（20260812）

| 编号 | 来源 | 遗留项 | 文件 | 状态 |
| --- | --- | --- | --- | --- |
| L-048 | R9 | topics 解析与 attendees 同类风险；report 解析失败无留痕 | services/misc.py | 待处理 |
| L-049 | R9 | 首尾花括号截取函数（与 knowledge_keeper 同病） | tools/distill_lessons.py | 待处理 |
| L-050 | R9 | 热点 sources 非 list 时 s.get 崩溃 | tools/knowledge_keeper.py | 待处理 |
| L-051 | R9 | resolve 对 LIKE 通配符未转义；docstring 示例与 CLI 不符 | tools/novel_knowledge.py | 待处理 |
| L-052 | R9 | upsert_chapters 对元素无 dict 防线 | tools/record_work.py | 待处理 |
| L-053 | R9 | n8n_api Cookie 重复附加；token 静默作废缓存陈旧 | tools/n8n_api.py | 待处理 |
| L-054 | R9 | _run_fix_worker 建议 stdin 传任务 | scripts/_run_fix_worker.ps1 | 待处理（低） |
| L-055 | R9 | delete_book reply_to 回复链 ref 全 0 残留 | tools/delete_book.py | 待处理（低） |
| L-056 | R9 | ai_taste_check detect 非字符串输入 TypeError | tools/ai_taste_check.py | 待处理 |
| L-057 | R9 | 测试普遍不清理 mkdtemp 目录 | tests/ | 待处理 |
| L-058 | R9 | 预检失败不写 failed_nodes（链路图精度） | editorial_daily/preflight | 待处理 |

## 第十轮遗留更新（20260812）

| 编号 | 来源 | 遗留项 | 文件 | 状态 |
| --- | --- | --- | --- | --- |
| L-048 | R9 | topics 解析 / report 留痕 | services/misc.py | 已修（R10-A1-02） |
| L-049 | R9 | distill 花括号截取 | distill_lessons.py | 已修（R10-C1-01） |
| L-050 | R9 | 热点 sources 非 list | knowledge_keeper.py | 已修（R10-C1-02） |
| L-051 | R9 | resolve LIKE 转义 + docstring | novel_knowledge.py | 已修（R10-C1-03） |
| L-052 | R9 | upsert_chapters dict 防线 | record_work.py | 已修（R10-C1-05） |
| L-053 | R9 | n8n Cookie 重复 / token 陈旧 | n8n_api.py | 已修（R10-C2-02） |
| L-054 | R9 | worker stdin 传任务 | _run_fix_worker.ps1 | 已修（R10-C2-01） |
| L-055 | R9 | delete_book reply 链残留 | delete_book.py | 已修（R10-C2-03） |
| L-056 | R9 | ai_taste 非字符串 TypeError | ai_taste_check.py | 已修（R10-C1-04） |
| L-057 | R9 | 测试 mkdtemp 清理 | tests/ | 待处理 |
| L-058 | R9 | 预检失败不写 failed_nodes | editorial_daily | 已修（R10-A2-07） |
| L-059 | R10 | knowledge_drafts accept 分支 ValueError 未捕获 | web_api.py | 待处理 |
| L-060 | R10 | /api/knowledge 等 conn 未关闭（请求泄漏） | web_api.py | 待处理 |
| L-061 | R10 | workday resume 可能重复写日记 | workday.py | 待处理 |
| L-062 | R10 | novel_knowledge.get() entity LIKE 未转义 | novel_knowledge.py | 待处理 |
| L-063 | R10 | record_work 活动统计 c.get 裸调 / upsert_characters 无防线 | record_work.py | 待处理 |
| L-064 | R10 | get_meta sources dict 崩溃 / top_keywords 非 list | get_meta.py | 待处理 |

## 第十一轮遗留更新（20260812）

| 编号 | 来源 | 遗留项 | 文件 | 状态 |
| --- | --- | --- | --- | --- |
| L-059 | R10 | knowledge_drafts accept ValueError 500 | web_api.py | 已修（R11-A1-03） |
| L-060 | R10 | 知识端点 conn 泄漏 | web_api.py | 已修（R11-A1-04） |
| L-061 | R10 | workday resume 重复日记 | workday.py | 已修（R11-A2-08） |
| L-062 | R10 | get() entity LIKE 未转义 | novel_knowledge.py | 已修（R11-C-05） |
| L-063 | R10 | record_work 活动统计/upsert_characters 防线 | record_work.py | 已修（R11-D-05） |
| L-064 | R10 | get_meta sources/top_keywords | get_meta.py | 已修（R11-D-07） |
| L-065 | R11 | 会议创建未收敛单一入口（CLI 绕过锁） | agent_meeting/misc | 待处理 |
| L-066 | R11 | /api/novel_knowledge upsert 错误语义 200+ok:false | web_api.py | 待处理 |
| L-067 | R11 | completed_with_pending 未映射（daily_runs/flow_graph） | daily_runs.py/flow_graph.py | 待处理 |
| L-068 | R11 | 锁与告警路径硬编码 ROOT | control/editorial_daily/preflight | 待处理 |
| L-069 | R11 | desktop api-error 通道未桥接 preload/webapp | desktop | 待处理 |
| L-070 | R11 | export 全节点缺失 exit 0 / distill 元素缺字段静默 | export_agent_prompts/distill_lessons | 待处理 |
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
