# 分片审查汇总 · 20260812-2224

## core

### P2（1）
- [P2] Same-second event_id collision silently drops free-meeting user messages — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:168-176

### P3（3）
- [P3] Idle free sessions are reaped as failed after the 60-min heartbeat timeout while their loop is still alive — E:/code/novel-editorial/novel_editorial/services/meeting_session.py:123-141
- [P3] New meeting web endpoints have no test coverage — E:/code/novel-editorial/novel_editorial/web_api.py:307-374
- [P3] Meeting SSE endpoint lacks the connection cap and bound that _sse has — E:/code/novel-editorial/novel_editorial/web_api.py:307-335

## editorial

### P2（2）
- F1 | P2 | daily_runs 状态/面板/HTML 报告 | scheduled 触发 + daily_enabled=false 的 workday | 零产出日显示"上次成功"，ok=True |
- F2 | P2 | 自由会议会话生命周期 | 用户 >60 分钟不发言 | 会话被误标 failed，后续事件静默丢弃 |

### P3（3）
- F3 | P3 | 自由会议可靠性 | LLM 持续失败触发压缩 | worker 静默死亡、事件丢失 |
- F4 | P3 | 存稿发布诊断 | 单章发布失败 | 链路图不标红、无错误详情 |
- F5 | P3 | dry-run 语义 | 存在陈旧 workday 行时执行 dry-run | 真实行被标记 failed |

## frontend

### P2（3）
- [P2] Refetch full message history after SSE reconnect in useMeetingStream — E:\code\novel-editorial\webapp\src\lib\use-meeting-stream.js:80-81
- [P2] Clear finished session so meetings page returns to start form — E:\code\novel-editorial\webapp\src\pages\MeetingsPage.jsx:99-100
- [P2] Commit version bump in desktop release script before tagging — E:\code\novel-editorial\desktop\release.js:132-133

### P3（5）
- [P3] Remove dead closeToTray IPC channel in desktop preload — E:\code\novel-editorial\desktop\preload.js:11-11
- [P3] Load knowledge for initially selected novel in WorksPage — E:\code\novel-editorial\webapp\src\pages\WorksPage.jsx:35-44
- [P3] Wire or remove no-op 新建项目 button in WorksPage — E:\code\novel-editorial\webapp\src\pages\WorksPage.jsx:52-52
- [P3] Remove unused API wrappers and store fields (dead code) — E:\code\novel-editorial\webapp\src\api.js:121-129
- [P3] Set created_at for SSE live messages in meeting stream — E:\code\novel-editorial\webapp\src\lib\use-meeting-stream.js:57-57

## knowledge

（本分片无显式 P0-P3 条目）

## platform

### P1（2）
- [P1] Unify run-lock path: publish_stock/preflight use config.TMP_DIR while scheduler/release_lock use ROOT/n8n_tmp — E:\code\novel-editorial\tools\publish_stock.py:378-378
- [P1] Reader-stats/hot-topics/alerts paths diverge between CLI tools and web under NOVEL_DATA_DIR — E:\code\novel-editorial\tools\collect_reader_stats.py:23-23

### P3（1）
- [P3] collect_reader_stats.load_env skips inline-comment stripping used by every other env loader — E:\code\novel-editorial\tools\collect_reader_stats.py:51-51

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 2 |
| P2 | 6 |
| P3 | 12 |
