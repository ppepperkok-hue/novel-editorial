# 前端全量审查报告（2026-08-11）

## 审查范围与方法

审查 `webapp/src` 全部 13 个组件 + App 框架 + Electron 壳，逐模块对照
`novel_pipeline/web_api.py`、`services/*`、`tools/*`。

执行验证：

- `cd webapp && npm test` → 2 files / 6 tests passed
- `npm run build` → built in 2.17s
- `python run_tests.py` → 167 passed
- `node tools/validate_workflow_deep.mjs` → OK
- API 抽查 `/api/dashboard /control /agents /cost /executions /meetings
  /activity /agent_actions` → 字段与前端解构全部一致
- Electron `preload.js` 的每个 IPC 方法在 `main.js` 有对应 handler

## 总评

骨架健康：10 个导航页 + 命令面板全部接真实 API，无纯摆设页面；
前后端字段逐项核对一致，两轮审查未发现数据丢失类 P0。
主要问题集中在两处：实时通道覆盖轮询数据（P1）、展示数字与后端/工作流
实际值脱节（P2）。前端自动化测试覆盖明显不足（6 个用例只测框架与阅读器）。

## 问题清单

### P1

1. **执行记录列表被 SSE 快照截断成 5 条**
   证据：`web_api._snapshot_loop` 推送 `executions()[:5]`
   （web_api.py:64）；`ExecutionsPage` 的 `useEffect([snapshot])`
   用快照覆盖 `getExecutions` 的 30 条结果（ExecutionsPage.jsx:31-39）。
   影响：执行历史永远只显示最新 5 条。
   建议：快照只补头部/合并，或页面忽略快照覆盖。

2. **Dashboard「今日任务」用 UTC 日期**
   证据：DashboardPage.jsx `new Date().toISOString().slice(0,10)`，
   与 `published_at`（本地时间字符串）比较。
   影响：中国时区凌晨 0-8 点发布的章节被算成"今天没发布"。
   建议：用本地日期（如 `toLocaleDateString("sv")` 或手动格式化）。

### P2

3. **工作流节点数写死且互相矛盾**
   证据：Dashboard「60 节点 / 5 节点」（DashboardPage.jsx），
   Settings「61 节点 / 7 节点」（SettingsPage.jsx）；实际日更 65 节点。
   建议：后端返回节点数或去掉数字。

4. **手动补更上限不一致**
   证据：首页弹窗只提供 1-5 章（DashboardPage.jsx），后端
   `control.run_now` 允许到 10。
   建议：前端 1-10 或后端限 5，二选一。

5. **Settings「立即更新一章」文案误导**
   证据：按钮文案"立即更新一章"，实际触发完整日更工作流
   （按 daily_chapters/pending_publish，通常 2 章）。
   建议：文案改「立即补更（按每日章数）」。

6. **Settings 每批章数校验 1-4，后端允许 1-10**
   证据：SettingsPage `formValid` 限 `daily_chapters <= 4`，
   `check_stock.py` 允许到 10。
   建议：对齐上限。

7. **作品库「伏笔台账 / 剧情弧」区块无数据源**
   证据：`novels.outline` 实际只有
   `bible/blueprints/premise/genre/title/keywords/chapter1/chapter2`
   （实测 demo.db）；WorksPage 的 `o.foreshadowing/payoffs/arc` 永远为空。
   建议：从 blueprints 聚合伏笔展示，或移除该模块。

8. **前端测试覆盖不足**
   证据：`__tests__` 仅 6 个用例，覆盖 App 导航/命令面板/章节阅读器；
   Dashboard 卡片、Agent 管理、会议、成本、执行、设置等核心交互零覆盖。
   建议：至少为 P1 修复项补回归测试。

### P3

- Audit 页筛选缺 `knowledge` 分类（AuditPage.jsx CATEGORIES）。
- 命令面板缺 `audit` 页面命令（CommandPalette.jsx PAGE_CMDS）。
- MeetingLive `AGENT_NAMES` 缺 `knowledge_keeper`，点将选到时显示英文。
- ChaptersPage 状态筛选含 `queued/publishing/failed`，数据库无这些状态，
  永远 0。
- 侧栏「数据更新」恒显 —：dashboard payload 实测无 `updated_at`
  （dashboard keys 验证），仅 SSE 快照存在时有值。
- App 每 5 秒全量轮询 `/api/dashboard`（含热点/读者数据），可降频。
- KPI「连载作品」副标题写死「全部连载中」，存在 planning/finished 时不准确。
- Dashboard/Settings 工作流卡片无知识管家卡片（管理盲区）。
- WorksPage 手动绑定 `bindBook` 成功后页面状态未立即同步（依赖
  `getEndingStatus` 手动刷新，可接受但可优化）。

## 确认无问题的模块

- **Agent 管理页**：人格编辑/保存/渲染校验/部署、知识库、经验卡、会后任务、
  活动日志全部接真实 API；`/api/agents` 字段与组件一致。
- **会议中心**：发起/轮询/推进/结束/取消、完整对话回放、周会档案；
  `/api/meetings` 含 `session_id`，`/api/meetings/session` 可用。
- **成本中心**：`/api/cost` 返回 `by_day/by_node`，图表与表格真实。
- **阅读数据**：CSV 0-1 浮点 ×100 正确，低表现报告可用。
- **作品库主体**：大纲/角色卡/关系/世界观/设定知识库/成长轨迹可用。
- **章节阅读器 + AI 味检测**：正文加载、字号、检测评分可用。
- **热点采集**：`sources.books/titles` 双结构正确渲染，方法标签如实。
- **命令面板/主题/快捷键/错误边界**：均可用。
- **Electron 壳**：preload 与 main 的 IPC 方法一一对应；自动启动/托盘/退出
  均有实现。

## 验证记录

```
webapp: 2 files / 6 tests passed; build ok
backend: 167 tests passed
workflow: OK: all workflows valid
API keys:
  dashboard = chapters,cost_budget,health,hot_topics,novels,publish_logs,reader_stats,summary
  summary = chapters_draft,chapters_published,chapters_ready,chapters_total,
            monthly_cost,novels,publish_failed,quality_passed,quality_total
  control = workflows{daily,weekly} + settings(12 keys)
  agents[0] = description,file,model,name,nodes,prompt,synced,temperature
  cost = by_day,by_node
  executions[0] = id,started_at,status,stopped_at,workflow
  meetings[0] = action_items,attendees,blueprint_count,held_at,id,kind,
                novel_id,report,session_id,status,summary,topics,volume_goal_adjust
  activity = days,items
```

## 后续建议

1. 修复 P1-1（SSE 截断）与 P1-2（UTC 日期），各补一个前端回归测试。
2. 清理 P2：节点数改动态、上限对齐、文案修正、伏笔区块接数据或删除。
3. 补 P3 中影响使用的项（Audit 筛选、知识管家卡片）。
4. 将本报告作为 `docs/engineering/review-process.md` 的首个案例，
   后续审查按流程执行并归档到 `docs/reviews/`。

