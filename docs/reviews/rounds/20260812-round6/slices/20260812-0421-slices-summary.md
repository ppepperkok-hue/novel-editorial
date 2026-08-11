# 分片审查汇总 · 20260812-0421

## core

### P1（1）
- P1 | 计划任务指向垃圾 DB 路径，日更发布每天静默失败（空库 + exit 1，输出不可见）；面板却显示「已注册」 | Windows + 仓库与 DB 跨盘（桌面默认部署即此形态）；用户在面板保存定时设置 | 每次保存定时即注册坏任务，此后每天触发 |

### P3（2）
- P3 | 跨库会话静默漏跑，永久卡 running，无错误可见 | 以空 db_path 调 run_session 且会话不在默认库（当前无生产调用方） | 潜在 |
- P3 | 核心修复（JSON action_items）无测试保护 | 后续改动回归风险 | 维护期 |

## editorial

### P1（1）
- [P1] relations.ensure 在迁移库上必现 NOT NULL IntegrityError，导致日更整体失败 — E:\code\novel-editorial\tools\relations.py:44-49

### P2（2）
- [P2] _handle_outbox 对 LLM 输出做无防护 int() 转换，非数字 reply_to 会拖垮整次日更 — E:\code\novel-editorial\tools\editorial_daily.py:97-98
- [P2] daily() skipped 分支无条件删除 daily_runs 行，会删掉 workday 创建的工作日记录 — E:\code\novel-editorial\tools\editorial_daily.py:1656-1660

### P3（3）
- [P3] daily_runs.sync_from_n8n 无异常防护，n8n 本地库不可读时 executions 端点 500 — E:\code\novel-editorial\tools\daily_runs.py:56-70
- [P3] agent_meeting.main 中 apply_report 只捕获 ImportError/AttributeError，outline 损坏时会议 CLI 崩溃 — E:\code\novel-editorial\tools\agent_meeting.py:748-753
- [P3] editorial_state._scoped_ids 的 (0,) 分支不可达（死代码） — E:\code\novel-editorial\tools\editorial_state.py:11-13

## frontend

### P2（1）
- [P2] 桌面端每次启动都会对最近 30 条终态执行补发系统通知 — E:\code\novel-editorial\desktop\main.js:206-218

### P3（2）
- [P3] 手动刷新不再更新 dashboardError，失败静默、恢复后错误横幅最多残留 5 秒 — E:\code\novel-editorial\webapp\src\App.jsx:59-70
- [P3] webapp/.npmrc 提交了本机绝对路径缓存目录 — E:\code\novel-editorial\webapp\.npmrc:1-1

## knowledge

### P3（3）
- [P3] sync_latest 两条路径返回结构不一致，无章节分支缺少 skipped 键 — E:\code\novel-editorial\tools\novel_knowledge.py:601-608
- [P3] world_events 缺类型守卫，LLM 输出 dict 时事件被静默丢弃且无留痕 — E:\code\novel-editorial\tools\novel_knowledge.py:412-415
- [P3] 冲突草稿 title 前缀使升级前旧数据无法命中新去重查询，可能重复建草稿 — E:\code\novel-editorial\tools\novel_knowledge.py:114-119

## platform

### P1（1）
- [P1] record_work 对非 dict 的 character_updates 抛 AttributeError，当日归档静默丢失 — E:\code\novel-editorial\tools\record_work.py:166-166

### P2（1）
- [P2] get_meta 对合法 JSON 但形状错误的 outline/tags 崩溃，违反自身 _safe_json 契约 — E:\code\novel-editorial\tools\get_meta.py:72-72

### P3（3）
- [P3] collect_reader_stats 无匹配章节时用空表覆盖 reader_stats.csv，静默清空既有反馈数据 — E:\code\novel-editorial\tools\collect_reader_stats.py:147-152
- [P3] preflight acquire_lock 文档与实现的 2 小时陈旧规则互相矛盾 — E:\code\novel-editorial\tools\preflight.py:151-155
- [P3] n8n_api.py 硬编码 localhost:5678 与触发器名，忽略 N8N_BASE 配置 — E:\code\novel-editorial\tools\n8n_api.py:12-12

## tests

### P2（1）
- [P2] .env.example 行内注释导致配置静默回退失效 — E:/code/novel-editorial/.env.example:71-72

### P3（5）
- [P3] compliance_words.txt 全注释，发布扫描每次触发 EMPTY 警告 — E:/code/novel-editorial/compliance_words.txt:1-3
- [P3] quality_gate 对 ai_words.json 缺失/损坏静默回退无告警 — E:/code/novel-editorial/novel_editorial/quality_gate.py:33-34
- [P3] test_quality_gate 未钉住重叠词非重叠计数语义 — E:/code/novel-editorial/tests/test_quality_gate.py:14-16
- [P3] .env.example 与 config.py 硬编码真实 n8n 工作流 ID — E:/code/novel-editorial/.env.example:54-56
- [P3] run_tests.py 不收集 *_test.py 命名测试 — E:/code/novel-editorial/run_tests.py:8-11

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 3 |
| P2 | 5 |
| P3 | 18 |
