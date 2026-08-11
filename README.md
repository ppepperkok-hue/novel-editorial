# novel-pipeline · AI 网文自动生成与发布流水线

面向「番茄小说」副业场景的全自动网文流水线：n8n 定时编排 +
DeepSeek 11 位人格化 Agent 协作 + Python 记忆/知识层（SQLite）+
番茄 HTTP 发布 + Electron 桌面控制台。

目标场景：**每天 08:00 自动生成并发布两章**，月预算 100 元内全流程无人值守；
Cookie 失效、预算超限、重复触发等异常自动熔断并写告警。

当前状态：**已真实跑通端到端发布**，首部作品已在番茄上线
（2026-08-11）。仓库：https://github.com/ppepperkok-hue/novel-pipeline

## 核心指标

| 指标 | 数值 | 控制位置 |
| --- | --- | --- |
| 日更节奏 | 每天 2 章（约 2000-2200 字/章） | n8n 每日触发 + `settings.daily_chapters` |
| 月预算 | 100 元 | `settings.monthly_budget` + 预检熔断 |
| 成本单价 | pro 0.01 元 / flash 0.002 元每千 token | `~/.n8n/.env` 的 `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` |
| 平台 | 番茄小说（Cookie + CSRF 鉴权） | `~/.n8n/.env` 的 `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` |
| 发布方式 | 存稿池优先：有存货发存货，没存货现造 | `tools/check_stock.py` + `tools/publish_stock.py` |
| 健康线 | 存稿池 < 3 章触发断更预警 | `novel_pipeline/scheduler.py` 的 `SAFE_BACKLOG` |
| 测试基线 | 170 个后端 unittest + 8 个前端 Vitest | `python run_tests.py` / `cd webapp && npm test` |

## 架构总览

```text
[n8n 日更工作流 · 65 节点]            [n8n 周会工作流 · 8 节点]        [n8n 知识管家 · 4 节点]
  每日 08:00 / 手动 webhook             每周日 08:10 / 手动              每日 03:30 / 手动
  └备份 → 预检 → 查章节号 → 读本地资料   └采集热点(双轨)                 └读热点/知识包/草稿/质量反馈
  └Planner → 守护 → 写手 A/B → 润色      └读上下文(周会材料+简报)         └博闻维护知识库
  └审稿 → 读者审稿 → 主编终审 → 质量门   └开会(周记→点将→3轮→总结)        └市场类自动更新 / 技巧类走人工草稿
  └排版 → 新建草稿 → 保存内容 → 发布      └蒸馏经验 → 落盘决策
  └校验 → 复核 → 提炼剧情 → 汇总运行结果 └读当前书(数据库绑定)
  └记录作品 → 采集阅读 → 全员写日记 → 同步设定知识库 → 结束(释放锁)
                    └
                    ▼
  Python 本地代理 POST /api/agent/run（DeepSeek function calling）
  get_knowledge 通用知识包 / get_novel_knowledge 本书记定库
                    └
                    ▼
  SQLite：作品/章节/设定库/伏笔/角色进化/会议/日记/心情/行动项/活动日志/成本/审计
                    └
                    ▼
  web_api（127.0.0.1:8000）↔ Electron 桌面控制台（React + Vite + SSE 实时推送）
```

分层职责：

- **编排层（n8n）**：只负责时序与分支，所有业务逻辑在本地 Python 脚本执行；
  工作流 JSON 由 `tools/render_workflow.py` 从 Agent 提示词资产生成。
- **智能层（prompts/agents + tools/agent_tool_loop.py）**：11 位人格化 Agent，
  原生 function calling 按需调用知识工具；LLM 不直接联网，爬取/检索/落库
  全部由 Python 代码执行。
- **记忆层（SQLite）**：故事圣经、章节摘要、角色状态、伏笔台账、设定知识库
  （版本化）、Agent 日记/周记/心情、会议档案、会后任务、活动日志。
- **发布层（tools/publish_stock.py + create_book.py）**：直接调番茄作者后台
  HTTP API，Cookie + CSRF 鉴权，三步发布（新建草稿 → 保存内容 → 提交发布）。
- **展示层（webapp + desktop）**：React 单页 + Electron 桌面壳，SSE 实时推送，
  托盘常驻、开机自启可选。

## 快速开始

环境要求：Python 3.9+、Node.js 18+、n8n 2.8（自托管）、番茄作者账号。

```bash
# 1. 安装
cd novel-pipeline
python -m pip install -e .          # 或使用 uv
cd webapp && npm install && npm run build
cd ../desktop && npm install

# 2. 配置凭据 ~/.n8n/.env（见 .env.example）
#    DEEPSEEK_API_KEY / FANQIE_COOKIE / FANQIE_CSRF_TOKEN
#    COST_PRO_PER_1K / COST_FLASH_PER_1K / MONTHLY_BUDGET / N8N_API_KEY
#    PYTHON_EXE / PIPELINE_ROOT（n8n executeCommand 运行环境）
#    NODES_EXCLUDE=[]（n8n 2.x 默认禁用 executeCommand，必须设置）
#    PANEL_TOKEN（可选，写接口 Bearer 加固）

# 3. 启动 n8n（必须带项目环境，见 scripts/start_n8n.ps1）
powershell -ExecutionPolicy Bypass -File scripts/start_n8n.ps1

# 4. 启动控制台 API（8000 端口，Electron 会自动拉起）
python -m novel_pipeline.web_api --db demo.db --port 8000
python -m novel_pipeline.web_api --db demo.db --port 8001

# 5. 桌面控制台
launch_desktop.vbs

# 6. 部署工作流（先渲染，再推送 n8n；Agent 管理页也可一键部署）
python tools/render_workflow.py
node tools/validate_workflow_deep.mjs
```

完整测试（仅标准库，无需安装依赖）：

```bash
python run_tests.py                # 170 个后端测试
cd webapp && npm test              # 8 个前端测试
node tools/validate_workflow_deep.mjs   # 工作流深度校验
```

## 自动日更流水线（65 节点）

### 触发与预检

- n8n scheduleTrigger 每日 08:00（`settings.daily_run_time` 可改，保存后自动重部署）；
- 手动 webhook `/webhook/novel-manual-run`（首页「立即补更」、面板控制、命令面板）；
- `tools/preflight.py` 检查：Cookie 有效性、今日是否已发、月预算、运行锁、
  是否有可发布作品（无书直接 blocked，防止空转）。手动预检请加 `--no-lock`
  避免残留运行锁。

### 生成链路（A/B 双轨）

Planner（pro）出两章细纲 → 守护（flash）拦截 OOC/吃书/伏笔矛盾 →
写手 A/B（pro，正文）→ 润色 A/B（flash，去 AI 味）→ 审稿 A/B →
读者审稿 A/B → 主编终审 A/B → 质量门（通过才继续，失败走失败留痕）。
双轨互相隔离：一条失败不阻塞另一条；发布失败章节保留为 reviewed 可次日补发。

### 排版、发布与落库

- 排版节点从润色输出取正文，按段落切成 HTML；
- 新建草稿 → 保存内容 → 提交发布 → 校验 → 复核（番茄作者后台三步发布）；
- `record_work.py` 汇总运行结果落库（章节/成本/摘要），空载荷跳过防垃圾行；
- 收尾：采集阅读数据 → 全员写日记 → 同步设定知识库 → 结束释放锁。

## 多 Agent 系统（11 位）

| Agent | 文件 | 模型 | 职责 |
| --- | --- | --- | --- |
| 策划官 | planner.md | pro | 故事圣经与两章细纲（情绪/定位/伏笔埋收） |
| 世界观守护 | guard.md | flash | 动笔前拦截 OOC/吃书/时间线/伏笔矛盾 |
| 叙事写手 | writer.md | pro | 按细纲+角色卡+守护约束写正文（A/B 共用） |
| 文字编辑 | editor.md | flash | 去 AI 味、翻译腔、标点、节奏收紧 |
| 逻辑审稿 | reviewer.md | flash | 六类底线问题 + 风格检查 |
| 读者体验审稿 | reader.md | flash | 追读欲/钩子/情绪满足评分 |
| 主编终审 | eic.md | flash | 仲裁冲突，输出 verdict 与 must_fix |
| 记忆官 | memory.md | flash | 提取摘要、角色状态、事件、伏笔台账 |
| 作品资料 | work_meta.md | flash | 书名/简介/标签/主角/卷目标 |
| 完结评估 | ending_judge.md | flash | 完结评估：剧情进度、伏笔回收、收尾建议 |
| 知识管家 | knowledge_keeper.md | flash | 定时维护知识库、整合经验卡、审查热点 |

每位 Agent 人格文件含「人物档案」「日常任务」「日记模式」「周记模式」
「会议模式」五段指令，可从前端 Agent 管理页编辑、校验并部署。

### 工具式知识调用

`agent_tool_loop` 第一轮携带人格 + 知识索引 + `get_knowledge` /
`get_novel_knowledge` 工具声明；模型自主发 `tool_calls` 时本地检索知识包
并以 tool 消息回传后二次推理。正文类 Agent（写手/润色）关闭 JSON 强制模式，
长生成超时 300 秒。空 content 不再静默成功（返回失败并留痕，可重试）。

### 记忆与成长闭环

- `agent_diaries`：daily（每日日更后）+ weekly（周会前）+ meeting（会后）；
- `agent_states`：每周心情（satisfaction/concern/excitement/fatigue）；
- `agent_actions`：会后任务，状态机 pending → done/skipped，周会材料注入
  `my_pending_actions` 让 Agent 真正执行；
- `agent_activity`：全量活动日志（会议发言/总结/日记/行动项/写作/审稿/
  知识维护/日更归档），前端按天分组回看；
- 反思蒸馏：周会/专题会后自动把经验卡草稿落 `knowledge_drafts`，人工采纳
  后写入知识包。

## 会议系统（周会 / 专题会议）

- 周会：周日 08:10，写周记 → 主席点将 → 三轮通气 → 主席总结 → 蒸馏经验 →
  落盘决策（蓝图/读者画像/封面提示词/完结评估）；
- 专题会议：首页一键发起，每轮结束可插话指示，随时「结束并总结」；
  取消会议会真正终止后台线程（不会默默烧钱跑完）；
- 完整对话可回放：交互式与定时周会都写入 `meeting_sessions.transcript`，
  周会档案页逐轮查看；
- 新书选题会：无作品时开会，结论 `next_book` 自动落成 planning 新书，
  可在作品库确认创意 → 一键建书（番茄每日限 1 本）→ 绑定后日更切换。

## 知识体系

- `prompts/knowledge/*.md`：6 个通用写作知识包（开篇钩子/节奏爽点/人设关系/
  巧思伏笔/去 AI 味/市场选题），frontmatter 声明适用 Agent 与关键词；
- `novel_knowledge`：每书设定知识库，8 分类、版本化、可查可改，日更自动
  从 bible 初始化并增量同步；
- 知识管家「博闻」：每天 03:30 维护，市场类直接更新、技巧/经验类走人工
  草稿采纳；工具包更新草案可在 Agent 管理页审阅。

## 热点采集（HTML + 浏览器双轨）

纵横走 HTML 直抓，番茄/起点需要浏览器降级（bb-browser，自动重开页面）；
每次采集如实记录 method（html/browser/error）与书名清洗结果；首页
「立即采集」可手动触发，知识管家每周把热点整理进市场知识包。

## 自动建书与封面

- 新书会结论 → planning 新书 → 确认创意（ready）→ 一键建书（番茄
  create/v0，每日限 1 本）→ 自动绑定 book_id/volume_id；
- 封面提示词由会议生成，作品库可一键复制给豆包等文生图工具；
- 注意：番茄作者 API 部分接口要求 `msToken`/`a_bogus` 签名，直接 HTTP 调用
  建书会被拒；当前建书建议用浏览器页面操作（bb-browser），已记录待修。

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
| knowledge_drafts | 经验卡/知识包更新草稿 |
| audit_logs | 全量留痕（设置/操作/Agent/发布/会议/知识/预检） |

## 前端面板

10 个页面 + 命令面板（Ctrl+K）：

- 首页：流水线状态（待命/运行中/离线）、今日任务、上次执行、最近会议、
  工作流卡片（日更/周会/知识管家）、KPI、预算、健康检查、完读率、
  最近发布、热点选题、手动补更；
- 作品库：大纲/角色卡/关系/世界观/伏笔台账（按蓝图聚合）/设定知识库/
  成长轨迹/封面提示词/建书与绑定；
- 章节管理：筛选/阅读器/AI 味检测；
- Agent 管理：人格编辑/部署/知识库/经验卡/会后任务/活动日志；
- 会议中心：直播/取消/完整对话回放；
- 成本中心、执行记录、阅读数据、系统设置、留痕档案。

所有卡牌数据均接真实 API；执行状态与上次执行有 SSE + 轮询双通道兜底，
SSE 断开不会卡死在"待命"。

## 工程与审查

- 标准审查流程：`docs/engineering/review-process.md`（证据优先、字段对照、
  P0-P3 分级、报告模板）；
- 历史审查报告：`docs/reviews/`；
- 演进记录：`docs/evolution.md`；
- 架构说明：`ARCHITECTURE.md`；
- 多 Agent 协作设计：`docs/research/multi_agent_coordination.md`；
- 发布路径走查与修复清单：`docs/research/publish_path_review_20260810.md`。

## 已知限制与风险

- **n8n 2.8 默认禁用 executeCommand**：必须通过 `scripts/start_n8n.ps1`
  注入 `NODES_EXCLUDE=[]` 等项目环境变量启动，否则工作流无法激活；
- **运行环境断电**：断电会中断运行中的执行（标记 crashed）并可能残留
  运行锁，重启后需手动释放；建议避开断电高发时段设置日更时间；
- **番茄建书接口签名**：`msToken`/`a_bogus` 风控导致直接 HTTP 建书被拒，
  当前依赖浏览器页面操作建书（已记录待修）；
- **番茄每日限建 1 本**：删除旧书后当日额度可能不重置；
- **DeepSeek 空 content**：偶发，已做 5 次重试 + 失败留痕，不再静默
  产生空正文。

## 后续路线

### 已完成

- 端到端发布闭环（新书会 → 建书 → 日更 → 番茄发布 → 落库 → 日记 → 释放锁）；
- 多 Agent 协作闭环（行动项 + 活动日志 + 周会回放 + 记忆人格化）；
- 标准审查流程与两轮全量审查；
- 前端全部卡牌数据真实化与 SSE 断连兜底。

### 待做

- 番茄建书接口签名适配（抓真实请求修复 create_book.py）；
- 行动项自动回填（日更结果识别"待办已完成"）；
- 工具调用级活动日志（agent_tool_loop 每次检索落 activity）；
- 定时任务开机自启（n8n/web_api/面板）。
