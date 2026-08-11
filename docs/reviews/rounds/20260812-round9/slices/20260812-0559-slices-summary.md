# 分片审查汇总 · 20260812-0559

## core

### P2（2）
- [P2] 会议等待输入循环缺少 failed 状态退出条件，线程永久轮询 — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:579-587
- [P2] _fail_orphan_sessions 误杀等待输入的会议，转录与报告丢失 — E:/code/novel-editorial/novel_editorial/web_api.py:1179-1181

### P3（3）
- [P3] get_active_session 对 NULL heartbeat_at 抛 TypeError，导致会议端点 500 — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:113-113
- [P3] _origin_allowed 放行无端口本地 origin，可绕过面板 token 写保护 — E:/code/novel-editorial/novel_editorial/web_api.py:56-61
- [P3] load_meetings 解析 attendees 无异常保护，损坏数据导致 500 — E:/code/novel-editorial/novel_editorial/services/misc.py:116-116

## editorial

（本分片无显式 P0-P3 条目）

## frontend

### P2（1）
- [P2] API 自动重启计数永不重置，常驻托盘应用最终失去自愈能力 — E:\code\novel-editorial\desktop\main.js:101-106

### P3（6）
- [P3] desktop 的 api-error IPC 消息无任何接收方，错误提示依赖系统通知 — E:\code\novel-editorial\desktop\main.js:88-100
- [P3] ExecutionsPage 的 snapshot prop 从未使用，SSE 实时快照被丢弃 — E:\code\novel-editorial\webapp\src\components\ExecutionsPage.jsx:29-29
- [P3] 快捷键帮助文案声称 1–12，实际数字键只能直达 1–9 — E:\code\novel-editorial\webapp\src\App.jsx:101-102
- [P3] 章节正文加载失败被静默伪装成“正文未落库”，误导用户 — E:\code\novel-editorial\webapp\src\components\ChaptersPage.jsx:76-78
- [P3] fetchControl 轮询错误被吞，侧边栏调度器状态短暂假绿灯 — E:\code\novel-editorial\webapp\src\App.jsx:60-60
- [P3] 关键交互页面与 desktop 主进程无自动化测试覆盖 — E:\code\novel-editorial\webapp\src\components\SettingsPage.jsx:1-1

## knowledge

（本分片无显式 P0-P3 条目）

## platform

### P1（1）
- 1 | P1 | record_work.py:466 | 月度成本低估 50%+，预算闸门失真 | 生产 scheduler 每次运行（必现） |

### P2（1）
- 2 | P2 | record_work.py:341 | 归档崩溃、n8n 裸 traceback | 上游 seq 为非数字字符串 |

### P3（7）
- 3 | P3 | check_stock/publish_stock | 设置 0 仍发 1 章 | 用户显式设 0 |
- 4 | P3 | pyproject.toml:6 | 包元数据乱码 | pip show / 发布时可见 |
- 5 | P3 | preflight.py:48 | cookie 值混入注释 | .env 含内联注释 |
- 6 | P3 | n8n_api.py:49 | 每次请求重复登录 | 批量 CLI 操作 |
- 7 | P3 | watch_daily.py:35 | 监控标签偏差 | 面板查看时 |
- 8 | P3 | _run_fix_worker.ps1 | 空模型参数/超长命令行 | 未指定 -Model / 大任务文件 |
- 9 | P3 | delete_book.py:70-95 | 孤儿消息残留 | 删除绑定番茄的书 |

## tests

### P3（2）
- [P3] test_meeting_malformed_agency_does_not_crash 使用恒真断言 assertTrue(True) — E:\code\novel-editorial\tests\test_meeting_session.py:151-154
- [P3] test_ai_taste_check.py 仅 2 个测试，detect() 大部分分支无覆盖 — E:\code\novel-editorial\tests\test_ai_taste_check.py:1-31

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 1 |
| P2 | 4 |
| P3 | 18 |
