# 跨轮次遗留跟踪表

| 编号 | 级别 | 问题 | 位置 | 状态 |
| --- | --- | --- | --- | --- |
| L1 | P2 | scheduled 触发 + daily_enabled=false 时 workday 显示「上次成功」（假绿灯） | tools/editorial_daily.py:530 | 待处理 |
| L2 | P2 | desktop release.js 打 tag 前未提交版本号 bump | desktop/release.js:132 | 待处理 |
| L3 | P3 | desktop preload 死通道 closeToTray | desktop/preload.js:11 | 待处理 |
| L4 | P3 | WorksPage 初始选中作品不加载知识库 | webapp/src/pages/WorksPage.jsx:35 | 待处理 |
| L5 | P3 | WorksPage「新建项目」按钮无动作 | webapp/src/pages/WorksPage.jsx:52 | 待处理 |
| L6 | P3 | api.js 未使用的 API 包装与 store 字段（死代码） | webapp/src/api.js:121 | 待处理 |
| L7 | P3 | collect_reader_stats.load_env 未剥离行内注释 | tools/collect_reader_stats.py:51 | 待处理 |
| L8 | P3 | 会议 web 端点（events/messages/respond）缺直接 HTTP 测试 | novel_editorial/web_api.py:307 | 待处理（service 层已测） |
| L9 | P3 | 空闲 free 会话 heartbeat 不更新（事件驱动设计使然，watchdog 已豁免） | tools/meeting_free_loop.py | 已解决（豁免） |

规则：下一轮任务包显式处理每项或标注「不处理+原因」；同一项不允许连续两轮未跟进。
