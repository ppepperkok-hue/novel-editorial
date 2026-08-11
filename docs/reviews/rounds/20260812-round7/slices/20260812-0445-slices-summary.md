# 分片审查汇总 · 20260812-0445

## core

### P2（1）
- [P2] /api/daily_runs swallows sync_from_n8n error marker (silent failure) — E:\code\novel-editorial\novel_editorial\web_api.py:149-151

### P3（4）
- [P3] web_api default --db is CWD-relative while config.DB_PATH is ROOT-rooted (silent DB split) — E:\code\novel-editorial\novel_editorial\web_api.py:1167-1167
- [P3] update_state with missing agent raises IntegrityError -> HTTP 500 instead of 400 — E:\code\novel-editorial\novel_editorial\services\misc.py:257-265
- [P3] db.connect(':memory:') returns a connection with no tables — E:\code\novel-editorial\novel_editorial\db.py:346-364
- [P3] Manual hot-topics refresh blocks the HTTP thread and always reports ok — E:\code\novel-editorial\novel_editorial\services\control.py:438-456

## editorial

### P2（4）
- "title": "[P2] auto_fill_actions 的 publish_logs 证据未按 novel 过滤，跨书误标行动项为 done",
- "title": "[P2] write_diaries.write() 无单 agent 失败隔离，一次 LLM 失败中断全部日记与周会",
- "title": "[P2] 选题会(planning)在已有作品时被绑定到最新小说，apply_report 会改写该书数据",
- "title": "[P2] agent_meeting CLI 轮次循环无异常隔离，LLM 失败中止整场会议并遗留 running 会话",

### P3（2）
- "title": "[P3] export_flow_html 未映射 skipped 状态，最近一次跳过运行显示为「待命（暂无运行）」",
- "title": "[P3] flow_graph.FAILED_ALIAS 缺少 eic，主编分派失败无法在链路图中高亮",

## frontend

### P1（1）
- [P1] 安装包打包 tools/chrome-profile 泄漏浏览器会话数据 — E:\code\novel-editorial\desktop\package.json:31-37

### P2（1）
- [P2] 启动窗口期内二次启动会创建第二个窗口且第一个窗口泄漏 — E:\code\novel-editorial\desktop\main.js:269-285

### P3（4）
- [P3] 输入框内按问号键会弹出帮助弹窗 — E:\code\novel-editorial\webapp\src\App.jsx:101-105
- [P3] AI 味检测失败后无法重试 — E:\code\novel-editorial\webapp\src\components\ChaptersPage.jsx:81-86
- [P3] WorksPage 多处 getEndingStatus().then() 缺少 catch — E:\code\novel-editorial\webapp\src\components\WorksPage.jsx:302-302
- [P3] 后端 API 进程运行期崩溃后桌面端无感知、不自动恢复 — E:\code\novel-editorial\desktop\main.js:71-75

## knowledge

（本分片无显式 P0-P3 条目）

## platform

（本分片无显式 P0-P3 条目）

## tests

### P3（3）
- [P3] 为 ai_words.json / compliance_words.txt 增加真实文件内容守卫测试 — E:\code\novel-editorial\tests\test_quality_gate.py:35-51
- [P3] .env.example 补录 N8N_WORKFLOW_TRIGGER 与 PYTHONW_EXE 两个被实际读取的键 — E:\code\novel-editorial\.env.example:72-74
- [P3] .env.example 移除无任何引用的 FANQIE_VOLUME_NAME 死配置 — E:\code\novel-editorial\.env.example:21-21

## 统计

| 级别 | 数量 |
| --- | --- |
| P0 | 0 |
| P1 | 1 |
| P2 | 6 |
| P3 | 13 |
