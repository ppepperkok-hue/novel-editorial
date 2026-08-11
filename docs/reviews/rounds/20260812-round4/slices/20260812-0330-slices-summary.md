# 分片审查汇总 · 20260812-0330

## core

### P2（2）
- [P2] 字符串 action_items 使会后任务生成整体失败 — E:\code\novel-editorial\novel_editorial\services\activity.py:324-326
- [P2] 会议心跳 10 分钟阈值会误杀仍在运行的会话 — E:\code\novel-editorial\novel_editorial\services\meeting_session.py:99-101

### P3（4）
- [P3] 触发周会会污染日更防重复标志 manual_run_requested — E:\code\novel-editorial\novel_editorial\services\control.py:356-356
- [P3] n8n API key 进程内永久缓存，改 env 后不生效 — E:\code\novel-editorial\novel_editorial\services\n8n.py:52-58
- [P3] backup keep=0 时实际不删除任何旧备份 — E:\code\novel-editorial\novel_editorial\backup.py:31-31
- [P3] pick_port 候选端口全占用时未捕获绑定异常 — E:\code\novel-editorial\novel_editorial\desktop.py:36-41

## editorial

（本分片无显式 P0-P3 条目）

## frontend

### P0（1）
- [P0] 保存设置时 Windows 计划任务注册静默失败，自动日更永不触发 — E:\code\novel-editorial\webapp\src\components\SettingsPage.jsx:82-89

### P1（1）
- [P1] 桌面版安装到非 C 盘时保存设置必然 500，自动日更失效 — E:\code\novel-editorial\desktop\main.js:51-54

### P2（2）
- [P2] Agent 保存失败时校验详情分支不可达，用户看不到失败原因 — E:\code\novel-editorial\webapp\src\components\AgentsPage.jsx:171-181
- [P2] release.js 发布流程不先构建 webapp，会打包旧前端 — E:\code\novel-editorial\desktop\release.js:37-37

### P3（4）
- [P3] 托盘通知不覆盖 partial 状态，部分成功静默无提示 — E:\code\novel-editorial\desktop\main.js:179-179
- [P3] 快捷键帮助文案“1 – 8”与实际 12 个导航项不符 — E:\code\novel-editorial\webapp\src\components\Shell.jsx:141-141
- [P3] vite dev 模式无代理，npm run dev 无法联调后端 API — E:\code\novel-editorial\webapp\vite.config.js:1-20
- [P3] 配置 PANEL_TOKEN 后桌面托盘 POST 缺少 Authorization，功能静默失败 — E:\code\novel-editorial\desktop\main.js:122-141

## knowledge

### P1（2）
- [P1] clean_novel_knowledge --apply 在多个实体收敛到同一规范名时崩溃 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:203-211
- [P1] sync_from_chapters 重复同步仍无限 version+1 并膨胀 history 表 — E:\code\novel-editorial\tools\novel_knowledge.py:196-200

### P2（1）
- [P2] _merge_history 静默丢弃被合并行的 content，相似但内容不同的设定丢失 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:184-200

### P3（2）
- [P3] knowledge_keeper 自动更新无内容变化检测，每次运行都重写知识包并刷新 updated_at — E:\code\novel-editorial\tools\knowledge_keeper.py:158-183
- [P3] export_agent_prompts 非代理导出路径对 find() 无 -1 保护，格式不符时静默写坏文件 — E:\code\novel-editorial\tools\export_agent_prompts.py:60-73

## platform

### P1（1）
- [P1] record_work 二次记录同一章时 qrow["scores"] 抛 IndexError — E:\code\novel-editorial\tools\record_work.py:315-322

### P2（2）
- [P2] publish_batch 在书已标记 finished 后仍继续发布超额章节 — E:\code\novel-editorial\tools\publish_stock.py:290-311
- [P2] pyproject 声明 websocket-client 但 uv.lock 未更新，uv sync 会失败 — E:\code\novel-editorial\pyproject.toml:10-10

### P3（4）
- [P3] n8n_api.py 模块级读取 N8N_TMP_PW，未加载 ~/.n8n/.env 且报错无提示 — E:\code\novel-editorial\tools\n8n_api.py:7-9
- [P3] watch_daily.py 在 daily_runs 无记录时访问 exec['status'] 抛 KeyError — E:\code\novel-editorial\scripts\watch_daily.py:21-22
- [P3] install_daily_task.ps1 -Remove 不检查 schtasks 退出码，误报删除成功 — E:\code\novel-editorial\scripts\install_daily_task.ps1:33-34
- [P3] 遗留重命名脚本硬编码 E:\code 绝对路径且已完成使命，建议归档 — E:\code\novel-editorial\scripts\finish_rename.ps1:15-18

## tests

（本分片无显式 P0-P3 条目）

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 1 |
| P1 | 4 |
| P2 | 7 |
| P3 | 14 |
