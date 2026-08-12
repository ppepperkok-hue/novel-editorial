# 文学编辑部 · Novel Editorial

一个由 11 位人格化 Agent 组成的 AI 文学编辑部，面向「番茄小说」副业场景：工作日节拍、晨会分派、行为选择权、记忆/关系/情绪、九类会议、每书设定知识库，加上番茄 HTTP 发布与桌面控制台。目标形态是「你点开工，编辑部上班；你点收工，编辑部下班」，月预算 100 元内持续产出日更两章。

这不是流水线。流水线把内容当零件传送，编辑部让一群有名字、有记忆、有关系的人一起把书写出来——质量门、预算、平台规则仍然是不可绕过的底线，但写作本身是协作的结果。

仓库：<https://github.com/ppepperkok-hue/novel-editorial>

## 核心指标

| 指标 | 数值 | 控制位置 |
| --- | --- | --- |
| 日更章节 | 每天 2 章（约 2000–2200 字/章） | 开工主题「写稿 N 章」+ `settings.daily_chapters` |
| 月预算 | 100 元 | `settings.monthly_budget` + 预检熔断 |
| 成本单价 | pro 0.01 元 / flash 0.002 元每千 token | `~/.n8n/.env` 的 `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` |
| 发布平台 | 番茄小说（Cookie + CSRF 鉴权） | `~/.n8n/.env` 的 `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` |
| 发布方式 | 存稿池优先：有存稿发存稿，没存稿现造 | `tools/check_stock.py` + `tools/publish_stock.py` |
| 健康线 | 存稿 < 3 章触发断更预警 | `novel_editorial/scheduler.py` 的 `SAFE_BACKLOG` |
| 测试基线 | 578 个后端 unittest + 45 个前端 Vitest（数量以 run_tests.py 输出为准） | `python run_tests.py` / `cd webapp && npm test` |

## 编辑部的一天

开工即上班。整个编辑部收进一个生命周期：不开工，门关着，消息和议题可以积累但零成本；你点开工，门开了，这一天按节拍走：

1. **晨会分派**：主编读任务板、收件箱、承诺、昨日遗留和你留下的老板指令，宣布今日安排。
2. **主产出**：写稿（存稿优先）或按今日主题跳过。
3. **决策点**：主产出结束后不自动下班——面板提醒你「可以收工、开会或继续补跑」，由你决定。
4. **手动收工**：全员写当日日记、留明日待办、主编发收工公告，状态落库；有遗留就如实标出，明天晨会优先处理。

首页开工按钮可选今日主题：**写稿 N 章 / 整理日 / 开会日 / 自由安排**。三类桌面提醒在后台静默值守：编辑部还没开工、开工了但没发稿、今天的工作完成了等你收工。

## 编辑部成员（11 位）

| 编辑 | 文件 | 模型 | 职责 |
| --- | --- | --- | --- |
| 策划官 | planner.md | pro | 故事圣经与两章细纲（情绪/定位/伏笔埋收） |
| 世界观守护 | guard.md | flash | 动笔前拦截 OOC/吃书/时间线/伏笔矛盾 |
| 叙事写手 | writer.md | pro | 按细纲 + 角色卡 + 守护约束写正文（A/B 共用） |
| 文字编辑 | editor.md | flash | 去 AI 味、翻译腔、标点、节奏收紧 |
| 逻辑审稿 | reviewer.md | flash | 六类底线问题 + 风格检查 |
| 读者体验审稿 | reader.md | flash | 追读欲、钩子、情绪满足评分 |
| 主编终审 | eic.md | flash | 仲裁冲突、晨会分派、会议主席、收工公告 |
| 记忆官 | memory.md | flash | 提炼摘要、角色状态、事件、伏笔台账、压缩会议历史 |
| 作品资料 | work_meta.md | flash | 书名/简介/标签/主角/卷目标 |
| 完结评估 | ending_judge.md | flash | 完结时机评估：剧情进度、伏笔回收、收尾建议 |
| 知识管家 | knowledge_keeper.md | flash | 维护知识库、整合经验卡、整理热点 |

每个人物档案都包含姓名、身份、性格、说话风格、价值观、核心关注点、情绪基线、工作习惯、弱点与盲区、人际预设、激励源、私下想法，以及日常/日记/周记/会议/消息/认领六套模式。前端 Agent 管理页可以直接编辑和部署。

## 协作机制：说话算数

编辑部不是「提示词装饰」——agent 说的话会真正改变下一步：

- **主编分派生效**：晨会分派指令注入写手任务，写手知道主编今天要什么。
- **行为选择权**：写手可以接受、拒绝或提出替代方案（`TASK_RESPONSE_MODE` 灰度），主编裁决后任务真的改变；拒绝有理由、替代方案可执行，每轨最多一次、超限兜底。
- **消息回路**：同事留言可以携带 rework/clarify/defer 决策——重做会自动产生高优行动项，延后会进明日待办，原消息标记已处理。
- **认领兑现**：写手认领的任务会在动笔时被提起；交稿即兑现，没交稿涨摩擦、降信任。
- **关系与情绪**：分派参考关系快照（信任高的优先）、打回措辞随摩擦变化、心情注入语气——但情绪只影响表达，不硬性改变质量判断。
- **自主性白名单**：写报告、更新知识草稿、投议题、认领任务、提方案可以自主执行；发布、建书、删书、完结、采纳知识永远锁在授权分层之外，越权动作拒绝并留痕。
- **两级记忆**：每日日记、周会前的周记（参考上周）、会议记忆；观点变化沉淀为「观点演化」时间线，被打回率趋势进周会材料。

## 会议系统

- **周会**：主席点将 → 三轮通气（先回应他人再发言）→ 主席总结报告 → 蒸馏经验 → 落盘决策（蓝图/卷目标/封面）。发言六段结构：本周小结 → 感受 → 意见 → 顾虑 → 提案 → 优先级。
- **专题会议**：一键发起、按轮推进、每轮之间可插入你的指示、随时手动总结；无作品也能开（讨论第一本书写什么）；历史过长由记忆官增量压缩。
- **自由讨论**：事件驱动的自主发言模式——无需点名，编辑按「话题 × 个人关注点」自主接话、有权沉默、可主动抛议题；老板可 @指定必答、随时插话；冷场由编辑主动推进或主席拉回；agent 请求拍板时面板弹审批卡；长历史自动压缩为摘要锚点。与轮次模式一键切换。
- **九类会议**：编辑部例会、剧情碰头会、选题会、单章会诊、数据复盘会、收尾会、危机处理会、知识分享会、茶水间闲聊。材料、议程、会后动作按类型路由：事故会产经验草稿、学习会产知识草案、收尾会记录建议，写作指令注入下一章上下文。
- 轮次会议对话写入 `meeting_sessions.transcript`，自由会议消息写入 `meeting_messages`（增量、可流式），SSE 实时推送直播；未消费的议题提议自动转成行动项。

## 创作链路（主产出）

写稿日的主产出按这条链走，A/B 双轨互相独立、互不拖累：

备份 → 预检（Cookie/已发/预算/锁/作品）→ 查存稿（有货直接发布）→ 查章节号 → 读记忆包（圣经/蓝图/摘要/角色/伏笔/读者反馈/热点/编辑部最近共识）→ 作品资料 → Planner 出大纲 → 守护细纲 → 写手 A/B → 润色 A/B → 审稿 A/B → 读者审稿 A/B → 主编终审 A/B → 质量门（字数/终审/去 AI 味词表/合规词）→ 排版 → 番茄三步发布 → 提炼剧情（摘要/角色状态/伏笔台账）→ 全员日记 → 设定库同步 → 行动项回填。

一章质量门失败只在排版处短路，另一章照常发布；失败原因写库，次日可人工补发。

## 知识体系

- **通用写作知识包**（`prompts/knowledge/*.md`）：开篇钩子、节奏爽点、人设与关系、巧思伏笔、去 AI 味硬规则、市场与读者心理 6 包；短硬规则常驻，长文由 agent 通过 function calling 按需调用。
- **每书设定库**：按「设定即代码」思路，每部小说单独建库（角色/世界规则/物品/势力/地点/力量体系/剧情事实/时间线 8 类），版本化、可查可改；开书时从故事圣经初始化，日更时随章节增量同步；写作/审稿时按需检索，禁止凭记忆编造设定。实体名强制短名词规范，冲突内容落草案人工处理。
- **经验卡**：会议蒸馏与知识管家产出 `knowledge_drafts` 草案，前端预览、编辑、采纳（写入知识包并重新部署）、拒绝。
- **热点采集**：纵横/番茄/起点三源排行榜，HTML 直抓失败自动降级浏览器抓取，清洗反爬乱码，首页一键刷新，知识管家整理进市场知识包。

## 平台发布（番茄）

已实测规则：

1. 作者实名认证后才能发章节；
2. 建书 `POST /api/author/book/create/v0/`（每天限 1 本，作品审核通过后才能发章节）；
3. 每章三步：`new_article/v0`（拿 item_id）→ `cover_article/v0`（存草稿）→ `publish_article/v0`（提交审核）；
4. 标题必须形如「第 N 章 标题」（5–30 字，不带序号报 `-3007`）；
5. 正文至少 1000 字（推荐 2000–2200），不足报 `-2`；大段重复报 `-3026`；每日提交字数上限实测 9000+ 字报 `-1019`，日更两章约 4400 字安全；
6. 发布前合规扫描：内置通用违规词 + `compliance_words.txt` 自定义词库，命中即拦截不发布。

## 数据层（SQLite）

| 表 | 内容 |
| --- | --- |
| novels / volumes / chapters | 作品状态机 + 章节元数据 |
| chapter_content / chapter_summaries | 正文存档 + 摘要/角色状态 |
| characters / character_evolution | 角色卡 + 成长轨迹快照 |
| world_events / plot_threads | 世界事件与伏笔台账 |
| quality_reports / publish_logs | 质量报告 + 发布审计 |
| novel_knowledge / novel_knowledge_history | 每书设定库（版本化） |
| cost_logs / settings | 成本台账与系统设置 |
| agent_diaries / agent_states / agent_memories | 日记/周记/心情/观点演化 |
| agent_relations / agent_messages / agent_promises | 关系/消息/承诺 |
| agent_actions / agent_activity | 会后任务 + 全量活动日志 |
| daily_runs | 工作日状态机与运行留痕 |
| weekly_meetings / meeting_sessions | 会议档案 + 状态机（rounds/free 两种模式、摘要锚点） |
| meeting_messages / pending_interactions | 自由会议消息流（增量 + 索引）+ 审批/澄清待办 |
| knowledge_drafts | 经验卡/知识包更新草案 |
| audit_logs | 全量留痕 |

## 面板与桌面

React 面板 + Electron 原生窗口（托盘常驻、关窗隐藏、执行通知、开机自启、自动更新），SSE 实时推送 + 轮询双通道兜底。页面：

| 页面 | 内容 |
| --- | --- |
| 仪表盘 | 编辑部状态（待命/工作中/待决策/已收工/有遗留）、今日任务、开工主题选择、决策点三按钮、收工卡片、预算、健康、热点 |
| 作品库 | 大纲/角色卡/人物关系/世界观/伏笔台账、设定知识库、成长轨迹、封面提示词、建书与绑定 |
| 章节管理 | 状态筛选、字数/评分/修订、章纲、阅读器 + AI 味检测 + 编辑部评语 |
| Agent 管理 | 人格编辑、部署、知识库、经验卡、会后任务、活动日志、日记、观点演化 |
| 成本中心 | 日成本柱状图、按节点 Token/费用表、预算进度 |
| 执行记录 | 工作日留痕（状态/发布数/失败节点/错误详情），后端离线也可回看 |
| 链路 | React Flow 渲染创作链路拓扑 + 最近运行状态着色，导出离线 HTML |
| 阅读数据 | 完读率/追读率趋势、逐章数据、低表现章节反馈 |
| 会议中心 | 九类会议发起（轮次/自由讨论）、实时直播（SSE）、@指定、审批弹窗、插话/总结/取消、档案回放 |
| 系统设置 | 日更开关、预算、目标字数、风格微调、自动建书 |
| 留痕档案 | 全量事件审计，按类别筛选 |

## 快速开始

### 环境要求

- Python 3.9+（项目实际在 3.11 验证）；
- Node.js 18+（前端构建）；
- 番茄作者账号（已实名）；
- DeepSeek API Key。

### 安装

```bash
cd novel-editorial
python -m pip install -e .          # 或用 uv
cd webapp && npm install && npm run build
cd ../desktop && npm install
```

### 配置

把 `.env.example` 复制为 `~/.n8n/.env` 并填写：

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` | 番茄作者后台登录态（约 1–2 个月失效） |
| `FANQIE_BOOK_ID` | 番茄作品 ID（面板绑定可自动写入；`FANQIE_VOLUME_ID` 已弃用，无读取方） |
| `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` | LLM 成本单价（元/千 token） |
| `PYTHON_EXE` | 脚本运行环境（换机器只改这里） |
| `PANEL_TOKEN` | 可选；配置后非浏览器调用必须带 Bearer 头 |

### 启动

```powershell
# 1. 启动控制台 API（Electron 会自动拉起，也可手动）
python -m novel_editorial.web_api --db demo.db --port 8000

# 2. 桌面控制台
launch_desktop.vbs

# 3. 开机静默自启（可选）
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1        # 注册
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1 -DryRun   # 预览
powershell -ExecutionPolicy Bypass -File scripts/install_autostart.ps1 -Disable  # 卸载
```

### 开工

面板首页选择今日主题（写稿 N 章/整理日/开会日/自由安排）点击开工；主产出结束后停在决策点，收工、开会、继续补跑由你决定。命令行演练：

```bash
python tools/workday.py --action open --mode write --dry-run   # 全链占位演练
python tools/workday.py --action open --mode org               # 整理日
python tools/editorial_daily.py --db demo.db --trigger manual  # 兼容旧入口
```

### 测试

```bash
python run_tests.py                # 578 个后端测试（数量以 run_tests.py 输出为准）
cd webapp && npm test              # 45 个前端测试
```

## 目录结构

```text
novel-editorial/
├── novel_editorial/          # Python 库
│   ├── config.py            # 集中配置：路径 / env / 开关
│   ├── db.py                # SQLite 数据层与迁移
│   ├── llm_client.py        # 统一 LLM 客户端（DeepSeek / Mock）
│   ├── web_api.py           # HTTP 路由壳（业务在 services/）
│   ├── services/            # control / dashboard / meeting_session / agency / reminders / knowledge ...
│   └── hot_topics.py        # 热点采集（HTML + 浏览器双轨）
├── prompts/
│   ├── agents/              # 11 位人格化 Agent（人物档案 + 六套模式）
│   └── knowledge/           # 6 个通用写作知识包
├── tools/
│   ├── workday.py           # 编辑部工作日状态机（R4-1 核心）
│   ├── editorial_daily.py   # 主产出调度器（单入口）
│   ├── agent_meeting.py / meeting_kinds.py / meeting_materials.py / meeting_actions.py  # 轮次会议
│   ├── meeting_free_loop.py / meeting_executor.py / meeting_speaker.py  # 自由会议调度（事件驱动）
│   ├── meeting_mentions.py / meeting_interactions.py / meeting_events.py  # @路由 / 审批 / SSE 广播
│   ├── agent_tool_loop.py / agent_context.py / mailroom.py / relations.py / agency.py   # 协作
│   ├── novel_knowledge.py / knowledge_keeper.py / distill_lessons.py  # 知识体系
│   ├── preflight.py / check_stock.py / publish_stock.py / record_work.py ...
│   └── release_lock.py      # 异常残留锁释放
├── webapp/                  # React + Vite + Tailwind 前端（Vitest）
├── desktop/                 # Electron 壳
├── n8n/                     # 遗留工作流 JSON（回退备份）
├── scripts/                 # install_autostart.ps1 / install_daily_task.ps1 / inject_fanqie_cookie.py / watch_daily.py ...
├── docs/                    # evolution / planning / research / engineering / reviews
├── tests/                   # 578 个后端测试（unittest）
└── demo.db                  # 运行数据库（gitignore）
```

## 文档地图

- `ARCHITECTURE.md`：架构与数据流；
- `docs/evolution.md`：项目演进历史与设计取舍；
- `docs/engineering/review-process.md`：标准审查流程（证据优先、P0–P3 分级）；
- `docs/reviews/`：历次审查报告；
- `docs/planning/`：规划、平台规则清单、决策表、运行手册；
- `docs/research/`：多 Agent 协作、Skill 整合、去 AI 味等调研。

## 已知限制与风险

- **番茄建书接口风控**：`msToken` / `a_bogus` 可能导致直接 HTTP 建书被拒，当前依赖浏览器页面操作兜底；
- **番茄每日限建 1 本**：删除旧书后当日额度可能不重置；
- **Cookie 有效期**：约 1–2 个月，失效后需重新抓取替换；
- **异常关机/强制结束**：会中断运行中的执行并可能残留运行锁，重启后 `python tools/release_lock.py --db demo.db` 释放；
- **n8n 已退役**：工作流 JSON 归档于 `docs/legacy/`，`scripts/start_n8n.ps1` 保留为异常回退入口。

## 后续路线（候选，未承诺）

- **消息即时重做**：R1-2 的「重做」目前落为高优行动项由后续触发点兑现；如需管线内即时重写，需单独设计防循环机制；
- **多会议共识合并**：写作指令目前取最近一次会议；多会议共识合并列为候选增强；
- **番茄建书接口签名适配**：如风控策略变化，抓真实请求修复 `create_book.py`。
