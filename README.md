# novel-pipeline · AI 网文自动生成与发布流水线

面向「番茄小说」副业场景的全自动网文流水线：Python 日更调度器（Windows 计划任务可选定时） + DeepSeek 多 Agent 协作 + Python 记忆/知识层（SQLite）+ 番茄 HTTP 发布 + 桌面控制台。

目标场景是每天定时自动生成并发布两章，月预算 100 元内无人值守。Cookie 失效、预算超限、重复触发、章节数不足等异常会自动熔断并写入告警，不会把错误内容发上平台。

当前状态：**端到端链路已真实跑通**（新书会议 → 建书 → 日更生成 → 番茄发布 → 阅读数据回流 → 全员日记 → 知识库同步）；2026-08-11 完成去 n8n 迁移，业务由本地 Python 调度器执行，n8n 工作流 JSON 归档于 `docs/legacy/` 作为回退备份。

仓库：<https://github.com/ppepperkok-hue/novel-pipeline>

## 核心指标

| 指标 | 数值 | 控制位置 |
| --- | --- | --- |
| 日更章节 | 每天 2 章（约 2000–2200 字/章） | 调度器手动开工 + Windows 计划任务定时 + `settings.daily_chapters` |
| 月预算 | 100 元 | `settings.monthly_budget` + 预检熔断 |
| 成本单价 | pro 0.01 元 / flash 0.002 元每千 token | `~/.n8n/.env` 的 `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` |
| 发布平台 | 番茄小说（Cookie + CSRF 鉴权） | `~/.n8n/.env` 的 `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` |
| 发布方式 | 存稿池优先：有存稿发存稿，没存稿现造 | `tools/check_stock.py` + `tools/publish_stock.py` |
| 健康线 | 存稿 < 3 章触发断更预警 | `novel_pipeline/scheduler.py` 的 `SAFE_BACKLOG` |
| 测试基线 | 276 个后端 unittest + 8 个前端 Vitest | `python run_tests.py` / `cd webapp && npm test` |

## 功能总览

- **自动日更流水线**：`tools/editorial_daily.py` 单入口调度器，手动开工为主、Windows 计划任务可选定时（08:00 默认）；预检 → 查章节号 → 生成作品资料 → 出大纲 → 多 Agent 写作审稿 → 质量门 → 排版 → 番茄三步发布 → 阅读数据回流 → 全员写日记 → 同步设定知识库 → 释放运行锁；每次运行写入本地 `daily_runs` 留痕（运行中/成功/部分成功/失败 + 失败节点）。
- **链路可视化**：面板「链路」页用 React Flow 渲染调度器全拓扑（预检/分派/作品资料/大纲守护/A-B 双轨/发布链/收尾），叠加最近一次运行状态着色（成功绿/部分橙/失败红/运行中蓝/待命灰），不运行也能人工审查；可一键导出单文件自包含 HTML 报告离线查看。
- **A/B 双轨隔离**：同一批生成两章，两条链互相独立。一章质量门失败只在排版处短路，另一章照常发布；失败原因写库，次日可人工补发。
- **存稿池**：每天先查 `reviewed` 存稿，有货先发存货；多写的章节存着，发不出去就留到第二天，断更风险自动预警。
- **11 位人格化 Agent**：策划官、世界观守护、叙事写手、文字编辑、逻辑审稿、读者体验审稿、主编终审、记忆官、作品资料、完结评估、知识管家。每个 Agent 都有人物档案（姓名/身份/性格/说话风格/价值观/核心关注点/情绪基线）和日记、周记、会议三套模式。
- **工具式知识调用**：Agent 首轮携带 `get_knowledge` / `get_novel_knowledge` 工具声明，由 DeepSeek 原生 function calling 自主决定是否检索；本地检索命中后以 tool 消息回传，二次推理输出最终结果。长知识包不常驻提示词，需要时才取。
- **两级记忆**：每天日更后每位 Agent 自述写「当日日记」；周会前回顾本周日记与工作数据写「本周日记」，并参考上周周记形成跨周连续记忆；会议后还有会后记忆与行动项。
- **会议系统**：定时周会（主席点将 → 三轮通气 → 主席总结报告）和专题会议（一键发起、按轮推进、每轮之间可插入你的指示、随时手动总结）。完整对话写入 `meeting_sessions.transcript`，前端可逐轮回放。
- **每书设定知识库**：按卡帕西式「设定即代码」思路，每部小说单独建库（角色/世界规则/物品/势力/地点/力量体系/剧情事实/时间线 8 类），版本化、可查可改；开书时从故事圣经初始化，之后随每章提炼增量同步，Agent 写作/审稿时按需调用，避免吞设定。实体名强制短名词规范（≤16 字、禁止整句），写入时自动合并相似实体并把冲突内容落 `knowledge_drafts` 草案；`tools/clean_novel_knowledge.py` 可一键清理存量脏数据（dry-run + 自动备份）；提供版本历史与关系图谱接口（`/api/novel_knowledge/history`、`/api/novel_knowledge/graph`）。
- **热点采集**：纵横/番茄/起点三源排行榜，HTML 直抓失败自动降级浏览器抓取；结果清洗后做题材关键词统计，首页可一键刷新，知识管家定期整理进市场知识包。
- **自动建书与作品资料**：`work_meta` Agent 自动生成书名、简介、标签、主角名、卷目标，仅当书还是默认名或简介过短时提交修改；会议产出新书选题与封面提示词，作品库一键确认创意 → 一键建书 → 绑定 book_id/volume_id。
- **成本中心**：每次 LLM 调用按模型单价折算写入 `cost_logs`，前端按日/按节点看账，月度预算超限由预检直接熔断。
- **全量留痕**：设置变更、手动操作、Agent 活动、发布结果、会议、知识维护、预检全部写 `audit_logs`，前端「留痕档案」可查。
- **桌面控制台**：React 面板 + Electron 原生窗口，无浏览器标签页；托盘常驻、执行完成通知、开机自启可选、GitHub 自动更新。

## 架构

```text
┌──────────────────────────── 调度层：tools/editorial_daily.py ───────────────────────────┐
│  日更调度器（单入口 daily()）           后台流程：周会 / 知识管家 / 热点采集             │
│  手动开工（面板/托盘/CLI）               control.run_workflow_now("weekly")             │
│  定时：Windows 计划任务（可选）           control.run_knowledge_keeper                    │
│  备份→预检→查存稿→（发存稿|现造）→A/B 双轨→发布→汇总→收尾→释放锁；daily_runs 全程留痕     │
└────────────────────────────────────────┬──────────────────────────────────────────────┘
                                         │ 进程内直接调用（Python 库函数）
                    ┌────────────────────▼────────────────────────────────┐
                    │  执行层：tools/*.py + novel_pipeline/*（Python 3.11） │
                    │  所有业务逻辑在本地脚本，调度器只负责时序与分支           │
                    └────────────────────┬────────────────────────────────┘
                                         │ LLM 调用
    ┌────────────────────────────────────▼────────────────────────────────────┐
    │  智能层：prompts/agents/*.md（11 位 Agent，frontmatter 定义模型/温度）   │
    │  人格档案 + 日常任务 + 日记/周记/会议模式                                 │
    │  工具循环：首轮带 get_knowledge / get_novel_knowledge → 检索 → 二轮输出  │
    └───────────────┬──────────────────────────────┬──────────────────────────┘
                    │                              │
    ┌───────────────▼──────────────┐  ┌────────────▼──────────────────────────┐
    │  知识层：SQLite（demo.db）    │  │  发布层：番茄作者后台 HTTP API          │
    │  作品/章节/角色/伏笔/设定库    │  │  new_article → cover_article          │
    │  日记/心情/会议/行动项/成本/留痕│  │  → publish_article（Cookie+CSRF）      │
    └───────────────┬──────────────┘  └────────────────────────────────────────┘
                    │
    ┌───────────────▼─────────────────────────────────────────────────────────┐
    │  展示层：web_api（http.server，127.0.0.1:8000）+ React/Vite + Electron  │
    │  SSE 实时推送 + REST API；前端同时承载 Agent 提示词编辑、会议直播、知识库 │
    └─────────────────────────────────────────────────────────────────────────┘
```

分层原则：

- **调度层（tools/editorial_daily.py）** 只负责时序与分支，所有业务逻辑在本地 Python 脚本执行；`daily()` 进程内复用全部工具，运行状态落 `daily_runs`。n8n 已退役（2026-08-11），工作流 JSON 归档于 `docs/legacy/`，`scripts/start_n8n.ps1` 保留为回退入口。
- **智能层（prompts/agents + tools/agent_tool_loop.py）** 是 11 位人格化 Agent。LLM 不直接联网，爬取、检索、落库全部由 Python 代码执行。
- **记忆层（SQLite）** 保存故事圣经、章节摘要、角色状态、伏笔台账、设定知识库（版本化）、Agent 日记/周记/心情、会议档案、会后任务、活动日志。
- **发布层（tools/publish_stock.py + create_book.py）** 直接调番茄作者后台 HTTP API，Cookie + CSRF 鉴权，三步发布。
- **展示层（webapp + desktop）** 是 React 单页应用 + Electron 桌面壳，SSE 实时推送，托盘常驻。

## 调度器与后台流程

### 1. 日更调度器（`tools/editorial_daily.py`）

触发方式：

- 手动开工：面板「立即补更」、托盘菜单、命令面板（`/api/control` action `run_now` 后台线程执行）；
- 定时（可选）：`scripts/install_daily_task.ps1` 注册 Windows 计划任务，默认每日 08:00（`settings.daily_run_time` 可改，保存时自动更新计划任务）；`daily_enabled=false` 时定时跳过；
- 手动运行支持指定本次生成章数（上限 5，前后端已对齐）。

流程：

1. **备份数据库** → **预检**（`tools/preflight.py`：Cookie 有效性、今日是否已发、月预算、运行锁、是否有可发布作品；手动预检带 `--no-lock` 避免残留锁阻塞）。
2. **读当前书** → **查存稿**（`tools/check_stock.py`）：存稿充足时直接 `tools/publish_stock.py` 发布存稿并进入收尾；存稿不足才进入生成链。
3. **查章节号**：调番茄 `book_list/v0`，取 `chapter_number` 作为下一章序号，A = 第 N 章、B = 第 N+1 章。
4. **读本地资料**（`tools/get_meta.py`）：组装记忆包 = 故事圣经 + 蓝图 + 最近章节摘要 + 角色状态 + 活跃伏笔 + 已有标题 + 读者反馈 + 热点摘要 + 风格微调。
5. **生成作品资料**（work_meta，pro）：书名/简介/标签/主角名/卷目标，仅当书还是默认名或简介过短时调用番茄 `modify_book/v0` 提交修改。
6. **Planner 出大纲**（pro）：两章细纲，每章含 title（全书唯一）、outline、scenes、emotion、position、hook_type、hook、pacing、plant_foreshadow、recover_foreshadow、character_arc。
7. **守护细纲**（guard，flash）：动手前拦截 OOC、吃书、时间线冲突、伏笔矛盾。
8. **写手 A/B**（pro）：按细纲 + 角色卡 + 守护约束 + 记忆包写正文；B 章输入 A 章结尾原文与提炼，保证两章连贯。
9. **润色 A/B**（editor，flash）：去 AI 味、翻译腔、标点、节奏收紧，执行「去 AI 味」硬规则（`ai_words.json` 共享词表 + `prompts/knowledge/anti-ai-style.md`）。
10. **审稿 A/B**（reviewer）→ **读者体验审稿 A/B**（reader）→ **主编终审 A/B**（eic，输出 verdict + must_fix）。
11. **质量门 A/B**：正文 ≥ 500 字（推荐 2000–2200）且终审 `passed=true` 才继续；失败分支在排版处短路，另一章照常发布，失败原因写库。
12. **提炼剧情 A/B**（memory）：从成稿提取结构化摘要、角色状态变化、事件、伏笔台账，随「记录作品资料」写回数据库，供次日记忆包使用。
13. **排版 A/B**：按自然段切 HTML，无换行时按句读自动断段（80–140 字），避免整章变成一个 `<p>`。
14. **发布三步**：`new_article/v0`（拿 item_id）→ `cover_article/v0`（保存标题和正文）→ `publish_article/v0`（提交审核）；随后校验发布结果，失败保留 `reviewed` 状态供补发。
15. **汇总运行结果**（`tools/record_work.py`）：章节/成本/摘要/角色/伏笔落库，空载荷跳过防垃圾行。
16. **收尾**：采集阅读数据 → 全员写日记（11 位 Agent 各自自述，flash）→ 同步设定知识库（`tools/novel_knowledge.py`）→ **回填行动项**（`tools/auto_fill_actions.py`，按当日产出自动把已完成的会后任务标 done）→ 结束并释放运行锁。

### 2. 周会（`tools/agent_meeting.py`）

面板/托盘手动触发（`run_now` action `weekly`）后台依次执行：

采集热点 → 读上下文（本周数据 + 行动项 + 心情）→ **开会**（`tools/agent_meeting.py`：写周记 → 主席点将 → 三轮通气 → 主席总结报告）→ 蒸馏经验（`tools/distill_lessons.py`，落 `knowledge_drafts` 草稿）→ 落盘决策（`tools/apply_architect.py`：合并蓝图、读者画像、卷目标、封面提示词）。

### 3. 知识管家（`tools/knowledge_keeper.py`）

面板手动触发（`run_knowledge_keeper` action）执行：

- 市场类知识包：直接把最新热点整理进 `prompts/knowledge/market-and-reader.md`，自动更新并记审计；
- 技巧/规则类与经验整合：落 `knowledge_drafts` 草案，人工在前端采纳后才写入知识包并重新部署；
- 废弃建议：对过时知识包标 `deprecated`。

## Agent 系统（11 位）

| Agent | 文件 | 模型 | 职责 |
| --- | --- | --- | --- |
| 策划官 | planner.md | pro | 故事圣经与两章细纲（情绪/定位/伏笔埋收） |
| 世界观守护 | guard.md | flash | 动笔前拦截 OOC/吃书/时间线/伏笔矛盾 |
| 叙事写手 | writer.md | pro | 按细纲 + 角色卡 + 守护约束写正文（A/B 共用） |
| 文字编辑 | editor.md | flash | 去 AI 味、翻译腔、标点、节奏收紧 |
| 逻辑审稿 | reviewer.md | flash | 六类底线问题 + 风格检查 |
| 读者体验审稿 | reader.md | flash | 追读欲、钩子、情绪满足评分 |
| 主编终审 | eic.md | flash | 仲裁冲突，输出 verdict 与 must_fix |
| 记忆官 | memory.md | flash | 提炼摘要、角色状态、事件、伏笔台账 |
| 作品资料 | work_meta.md | flash | 书名/简介/标签/主角/卷目标 |
| 完结评估 | ending_judge.md | flash | 完结时机评估：剧情进度、伏笔回收、收尾建议 |
| 知识管家 | knowledge_keeper.md | flash | 定时维护知识库、整合经验卡、整理热点 |

每个 Agent 文件（`prompts/agents/*.md`）的 frontmatter 定义 `model` / `temperature` / `max_tokens`，正文依次是「人物档案」「日常任务」「日记模式」「周记模式」「会议模式」。前端 Agent 管理页可直接编辑、校验，保存后调度器运行时即时生效。

### 工具式知识调用

`tools/agent_tool_loop.py` 实现标准 function calling 循环：

1. 首轮 system = 人物档案 + 任务模式 + 知识索引（每个知识包一行）+ `get_knowledge` / `get_novel_knowledge` 工具声明；
2. 模型自主发 `tool_calls`（不传 `tool_choice`，兼容 DeepSeek V4 thinking 模式）；
3. 本地检索 `prompts/knowledge/*.md`（关键词匹配 + Agent 白名单过滤）或 `novel_knowledge` 设定库，以 `role:"tool"` 回传；
4. 二轮（不再给工具）输出最终结果；无工具调用则单轮返回；工具调用异常自动降级为无工具单轮。

正文章节类 Agent（写手/润色）关闭 JSON 强制模式，长生成超时放宽到 300 秒；空 content 不再静默成功，返回失败并留痕可重试。

### 记忆与成长闭环

- `agent_diaries`：daily（每日日更后全员自述）、weekly（周会前回顾本周 + 参考上周周记）、meeting（会后记忆）；保留最近 8 周自动清理。
- `agent_states`：每周心情（satisfaction / concern / excitement / fatigue），影响会议表达语气，不硬性改变决策权重。
- `agent_actions`：会后任务，状态机 pending → done/skipped；每次日更结束后 `tools/auto_fill_actions.py` 按当日产出（发布章节/质量门/设定库变更/角色成长）自动回填完成状态并写证据，LLM 失败时降级规则判定；周会材料注入 `my_pending_actions` 让 Agent 真正执行。
- `agent_activity`：全量活动日志（会议发言/总结/日记/行动项/写作/审稿/知识维护/知识检索/日更归档），每次工具检索（`knowledge_lookup`）独立落一条，前端按天分组回看。
- 反思蒸馏：周会/专题会议后自动把经验卡草稿落 `knowledge_drafts`，人工采纳后写入知识包并 render + deploy。
- 成长性：Agent 每轮都会把「这周干了什么、关键事件、发现、心情变化」写进周记，形成跨周连续记忆；知识管家持续把外部热点蒸馏成市场知识包。

## 会议系统

### 周会

定时（每周日 08:10）或手动触发，完整流程：

写周记（每位参会 Agent 回顾本周简报 + 全部 daily 日记 + 上周 weekly 日记，自述本周日记并输出心情）→ 主席点将（eic 读材料 + 简报 + 全员心情，决定参会者与议题）→ 三轮固定通气（每轮先回应他人再发表意见）→ 主席总结报告 → 蒸馏经验 → 落盘决策。

发言固定六段结构：`本周小结（基于我的周记）→ 我的感受 → 意见 → 顾虑 → 提案 → 优先级`；缺段重试一次。

### 专题会议

首页「会议中心」一键发起，主题任意（例如「下一卷剧情怎么发展」）。特点：

- 无作品时也可开会（`novel_id=0`），适合先讨论第一本书写什么；
- 每轮结束后停在「等待输入」，你可以插话给指示，再继续下一轮；
- 你随时手动「结束并总结」，不再锁死三轮；
- 历史过长时由记忆官增量压缩（`compress_history`），只带最近两条的缺陷已修复；
- 取消会议在轮次边界生效：当前发言会跑完（单次最长 300 秒），之后立即停止，不会进入下一轮；
- 完整对话写入 `meeting_sessions.transcript`，周会档案页逐轮回放。

## 知识体系

### 通用写作知识包（`prompts/knowledge/*.md`）

6 个知识包，frontmatter 声明适用 Agent、类型、关键词：

| 文件 | 内容 |
| --- | --- |
| opening-hooks.md | 开篇钩子、黄金三章、章末钩子 |
| pacing-and-satisfaction.md | 节奏、爽点、情绪曲线 |
| character-and-relationship.md | 人设、OOC 红线、人物关系 |
| foreshadowing-design.md | 巧思伏笔：误导/细节/反差/多义，埋收计划 |
| anti-ai-style.md | 去 AI 味硬规则、文本质感、标点 |
| market-and-reader.md | 市场选题、热点、读者心理（知识管家自动更新） |

必须执行的短硬规则（如去 AI 味黑名单）以 `generic` 类型常驻，长文按需调用。

### 每书设定知识库（`novel_knowledge`）

- 8 类分类：character / world_rule / item / faction / location / power / plot / timeline；
- 版本化：每次变更写 `novel_knowledge_history`，可查历史；
- 初始化：开书时从故事圣经（bible）同步；日更时从成稿章节增量提炼同步（`tools/novel_knowledge.py`）；
- 读取：Agent 通过 `get_novel_knowledge` 工具按主题检索，写正文/设计细纲/查设定一致性时调用，禁止凭记忆编造设定；
- 前端作品库可按书查看/编辑设定库。

### 经验卡（`knowledge_drafts`）

会议蒸馏产出 `lesson` 草稿，知识管家产出 `knowledge` 更新草案；前端 Agent 管理页可预览、编辑、采纳（写入知识包并 render + deploy）、拒绝。

## 热点采集

`novel_pipeline/hot_topics.py` 采集三个来源的排行榜：

- 纵横：HTML 直抓有效（实测约 40 条）；
- 番茄/起点：HTML 抓不到时自动降级 bb-browser（每次任务重新 open 页面，eval 提取书名，实测可用）；
- 每次采集如实记录每源 method（html/browser/error）、数量与更新时间；
- 清洗层处理番茄字体反爬乱码，按可见字符统计关键词，乱码直接丢弃不阻塞；
- 首页「热点选题」有「立即采集」按钮；日更写作上下文注入近期热点（截断到 1000 字符）；知识管家每周整理进市场知识包。

## 作品资料与自动建书

- 新书选题会：无作品时也能开，会议结论 `next_book` 自动落成 planning 新书；
- 作品库确认创意（ready）→ 一键自动建书（番茄 `create/v0`，每天限 1 本）→ 自动绑定 book_id / volume_id；
- 封面：会议生成封面提示词，作品库一键复制给豆包等文生图工具，人工上传；
- 删除：作品库每本书可「删除番茄书籍」（二次确认 + 后端 confirm 双保险）；删除前先查 `book_detail` 的 `can_delete`（签约中的书平台不让删），成功后本地作品行与全部关联数据（章节/角色/设定库/日记等）一并清空；
- 建书请求已按番茄作家后台真实请求对齐（2026-08-11 抓包验证）：`category` 传主分类 ID、`group_category_id` 传主分类 ID、`roles` 传 JSON 数组、`activity_id` 自动选默认征文活动、`thumb_uri` 用平台默认封面；标签列表来自 `category_list`（`label` 区分主分类/主题/角色/情节），不再使用旧的 `category_id`/`label_id_list`/`protagonist_name_*` 字段。该接口无需 `msToken`/`a_bogus` 签名，Cookie + CSRF 即可直接 HTTP 建书。

## 发布链路（番茄）

已实测的番茄发书规则：

1. 作者实名认证（账号后台完成）后才能发章节；
2. 建书：`POST /api/author/book/create/v0/`（每天限 1 本，作品信息审核通过后才能发章节）；
3. 每章三步：
   - `POST /api/author/article/new_article/v0/` → 返回 `item_id` + `volume_id`；
   - `POST /api/author/article/cover_article/v0/` → 保存标题和正文（草稿）；
   - `POST /api/author/article/publish_article/v0/` → 提交审核。

规则：

- 标题必须形如「第 N 章 标题」（5–30 字），不带序号会报 `-3007`；
- 正文至少 1000 字（推荐 2000–2200），不足报 `-2 章节字数不足`；
- 大段重复内容报 `-3026`；
- 每日提交字数有上限（实测 9000+ 字后报 `-1019`），日更两章约 4400 字安全；
- 查询接口：`chapter_list/v1`（已发布）、`draft_list/v1`（草稿）、`book_list/v0`（`chapter_number` 是下一章号）。
- 发布前合规扫描：内置通用违规词（违禁品/赌博/诈骗/暴恐/色情露骨/代充广告）
  + `compliance_words.txt` 自定义词库，命中即拦截不发布（质量门之后执行）。

## 数据层（SQLite）

| 表 | 内容 |
| --- | --- |
| novels / volumes / chapters | 作品状态机 + 章节元数据 |
| chapter_content / chapter_summaries | 正文存档 + 摘要/角色状态 |
| characters / character_evolution | 角色卡 + 成长轨迹快照 |
| world_events / plot_threads | 世界事件与伏笔台账 |
| quality_reports / publish_logs | 质量报告 + 发布审计（成功/失败/AI 声明） |
| novel_knowledge / novel_knowledge_history | 每书设定库（版本化） |
| cost_logs / settings | 成本台账与系统设置 |
| agent_diaries / agent_states | 日记/周记/会议记忆 + 心情 |
| agent_actions / agent_activity | 会后任务 + 全量活动日志 |
| weekly_meetings / meeting_sessions | 周会档案 + 会议状态机（含完整 transcript） |
| knowledge_drafts | 经验卡/知识包更新草案 |
| audit_logs | 全量留痕（设置/操作/Agent/发布/会议/知识/预检） |

## 前端面板与桌面应用

### 面板（React + Vite + Tailwind）

11 个页面 + 命令面板（Ctrl+K）：

| 页面 | 内容 |
| --- | --- |
| 仪表盘 | 流水线状态（待命/运行中/上次失败/暂停）、今日任务、上次执行、最近会议、流程卡片（日更开关/周会/知识管家）、预算进度、健康检查、完读率、最近发布、热点选题、手动补更 |
| 作品库 | 大纲/角色卡/人物关系/世界观/伏笔台账（按蓝图聚合）、设定知识库、成长轨迹、封面提示词、建书与绑定 |
| 章节管理 | 状态筛选（草稿/审稿/待发布/已发布）、字数/评分/修订、章纲详情、阅读器 + AI 味检测 |
| Agent 管理 | 人格编辑（人物档案/三模式提示词/模型/温度）、部署、知识库、经验卡、会后任务、活动日志、日记 |
| 成本中心 | 日成本柱状图、按节点 Token/费用表、预算进度 |
| 执行记录 | 本地持久化的日更运行留痕（状态/发布数/失败节点/错误详情），后端离线也可回看 |
| 链路 | React Flow 渲染调度器全拓扑 + 最近运行状态着色，支持导出离线 HTML 报告 |
| 阅读数据 | 完读率/追读率趋势、逐章数据、低表现章节反馈 |
| 会议中心 | 发起专题会议、直播围观（每轮发言）、插话/总结/取消、周会档案回放 |
| 系统设置 | 日更开关、预算、目标字数、每日更新时间（保存后自动注册/更新计划任务）、风格微调、自动建书、开机会话 |
| 留痕档案 | 全量事件审计，按类别筛选 |

所有卡片数据接真实 API；执行状态与上次执行走 SSE + 轮询双通道兜底，SSE 断开不会卡在「待命」。

### 桌面壳（Electron）

- 原生窗口（无边框自绘标题栏），托盘常驻，关窗隐藏不退出；
- 托盘菜单：打开控制台 / 立即更新一章 / 立即跑周会 / 退出；
- 执行完成系统通知（成功/失败）；
- 开机自启可开关（系统设置页）；
- 打包后自动更新（electron-updater + GitHub Releases）；
- 打包时把 Python 侧代码、前端产物和 demo.db 作为 extraResources 带入。

### 备选入口

- 纯浏览器：`python -m novel_pipeline.web_api --db demo.db --port 8000`；
- pywebview 原生窗（旧版后备）：`python -m novel_pipeline.desktop`。

## 快速开始

### 环境要求

- Python 3.9+（项目实际在 3.11 验证）；
- Node.js 18+（前端构建）；
- 番茄作者账号（已实名）。

### 安装

```bash
cd novel-pipeline
python -m pip install -e .          # 或用 uv
cd webapp && npm install && npm run build
cd ../desktop && npm install
```

### 配置

把 `.env.example` 复制为 `~/.n8n/.env` 并填写：

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（会议/日记/工具循环使用） |
| `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` | 番茄作者后台登录态（约 1–2 个月失效，失效后重新抓取） |
| `FANQIE_BOOK_ID` / `FANQIE_VOLUME_ID` | 番茄作品/分卷 ID（也可由面板绑定自动写入） |
| `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` | LLM 成本单价（元/千 token） |
| `MONTHLY_BUDGET` | 月度预算熔断值 |
| `N8N_API_KEY` | 仅回退到 n8n 时需要（调度器模式不需要） |
| `PYTHON_EXE` / `PIPELINE_ROOT` | 脚本运行环境（换机器只改这里） |
| `PANEL_TOKEN` | 可选；配置后非浏览器调用（脚本/API）必须带 Bearer 头 |

### 启动

```powershell
# 1. 启动控制台 API（Electron 会自动拉起，也可手动）
python -m novel_pipeline.web_api --db demo.db --port 8000

# 2. 桌面控制台
launch_desktop.vbs

# 3. 开机自启（可选）：web_api:8000 随登录自动拉起
#    面板自启用系统设置页「开机自动启动」开关
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1        # 注册
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1 -DryRun   # 预览
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1 -Disable  # 卸载

# 4. 注册日更定时任务（可选，默认每日 08:00；不注册则纯手动开工）
powershell -ExecutionPolicy Bypass -File scripts/install_daily_task.ps1 -Time "08:00"
```

### 手动运行日更

```bash
python tools/editorial_daily.py --db demo.db --trigger manual
python tools/editorial_daily.py --db demo.db --trigger manual --dry-run   # 全链占位演练
```

导出链路报告（自包含 HTML，可离线审查/分享）：

```bash
python tools/export_flow_html.py --db demo.db
```

### 回退到 n8n（仅异常情况）

```bash
powershell -ExecutionPolicy Bypass -File scripts/start_n8n.ps1
python tools/render_workflow.py && node tools/validate_workflow_deep.mjs
```

### 测试

```bash
python run_tests.py                # 276 个后端测试
cd webapp && npm test              # 8 个前端测试
node tools/validate_workflow_deep.mjs   # 遗留工作流深度校验（回退路径）
```

## 目录结构

```text
novel-pipeline/
├── novel_pipeline/          # Python 库
│   ├── config.py            # 集中配置：路径 / env 加载 / 常量
│   ├── db.py                # SQLite 数据层与迁移（23 张表）
│   ├── llm_client.py        # 统一 LLM 客户端（DeepSeek / OpenAI 兼容 / Mock）
│   ├── web_api.py           # HTTP 路由壳（业务在 services/）
│   ├── services/            # 服务层：control / dashboard / agents / meeting_session / knowledge / activity / audit ...
│   ├── hot_topics.py        # 热点采集（HTML + 浏览器双轨）
│   ├── quality_gate.py      # 质量门
│   └── desktop.py           # pywebview 后备桌面入口
├── prompts/
│   ├── agents/              # 11 位人格化 Agent（人物档案 + 四种模式）
│   └── knowledge/           # 6 个通用写作知识包（frontmatter + 正文）
├── tools/                   # 流水线脚本与调度器
│   ├── editorial_daily.py   # 日更调度器单入口（de-n8n 核心）
│   ├── editorial_steps.py   # 节点逻辑纯函数（质量门/大纲/排版/汇总）
│   ├── flow_graph.py        # 链路拓扑与失败节点映射
│   ├── export_flow_html.py  # 自包含 HTML 链路报告
│   ├── daily_runs.py        # 本地运行留痕（调度器自写 + n8n legacy 同步）
│   ├── render_workflow.py   # Agent 资产 → 工作流 JSON（代理模式）
│   ├── validate_workflow_deep.mjs  # 工作流深度校验
│   ├── preflight.py / check_stock.py / publish_stock.py   # 日更控制
│   ├── agent_meeting.py / write_diaries.py / architect_weekly.py / apply_architect.py  # 会议与记忆
│   ├── agent_tool_loop.py   # 工具式知识调用循环
│   ├── novel_knowledge.py / knowledge_keeper.py / distill_lessons.py  # 知识体系
│   ├── auto_fill_actions.py # 日更后按产出自动回填会后行动项
│   ├── create_book.py / get_meta.py / record_work.py / collect_reader_stats.py ...
│   └── release_lock.py      # 异常残留锁释放
├── webapp/                  # React + Vite + Tailwind 前端（Vitest 测试）
├── desktop/                 # Electron 壳（main/preload/release.js）
├── n8n/                     # 遗留工作流 JSON（回退备份；docs/legacy/ 另有归档）
├── scripts/                 # install_daily_task.ps1 / install_autostart.ps1 / watch_daily.py ...
├── docs/                    # evolution / planning / research / engineering / reviews
├── tests/                   # 276 个后端测试（unittest）
└── demo.db                  # 运行数据库（gitignore）
```

## 文档地图

- `ARCHITECTURE.md`：架构与数据流；
- `docs/evolution.md`：流水线演进历史与设计取舍；
- `docs/engineering/review-process.md`：标准审查流程（证据优先、P0–P3 分级）；
- `docs/reviews/`：历次审查报告；
- `docs/planning/`：原始规划、平台规则清单、决策表、运行手册；
- `docs/research/`：多 Agent 协作、发布路径审查、Skill 整合、去 AI 味等调研。

## 已知限制与风险

- **n8n 已退役**：业务由 Python 调度器执行；仅当调度器出现无法快速修复的问题时，才按 README「回退到 n8n」一节启动遗留工作流；
- **调度器与 n8n 共用同一把运行锁**：回退期间两者不会并发双发；
- **番茄建书接口签名**：`msToken` / `a_bogus` 风控导致直接 HTTP 建书可能被拒，当前依赖浏览器页面操作（已登记待修）；
- **番茄每日限建 1 本**：删除旧书后当日额度可能不重置；
- **番茄每日提交字数上限**：实测 9000+ 字后报 `-1019`，日更两章安全；
- **Cookie 有效期**：约 1–2 个月，失效后需重新抓取替换；
- **异常关机/强制结束**：会中断运行中的执行（标记 crashed）并可能残留运行锁，重启后 `python tools/release_lock.py --db demo.db` 释放；
- **建书依赖浏览器**：自动建书链路可用性取决于番茄风控策略变化。

## 后续路线

- **编辑部人格化**（第一优先）：Agent 消息协作（mailroom）、叙事/人际记忆、两级完工状态机；
- **审稿打回重写**：调度器内建「审稿失败 → 打回重写 → 回审」回环（重试上限可配置）；
- **完结机制**：`ending_judge` 接入调度器周检，与收尾决策、完结停更、新书孵化绑定；
- **统一留痕**：全类别 `audit_logs` 回填、前端留痕档案；
- **人物卡进化**：`character_evolution` 成长轨迹随剧情推进更新，周会固化角色卡；
- **番茄建书接口签名适配**（抓真实请求修复 `create_book.py`，如风控策略变化）。
