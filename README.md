# 文学编辑部 · Novel Editorial

一个由 11 位人格化 Agent 组成的 AI 文学编辑部：你点开工，编辑部上班；你点收工，编辑部下班。工作日节拍、晨会分派、行为选择权、两级记忆（日记/周记）、人际关系与情绪、轮次与自由讨论两种会议形态、每书设定知识库，加上番茄 HTTP 发布与桌面控制台。定位是月预算 100 元内的持续副业产出（日更两章），同时这套「编辑部」骨架可以泛化到小说之外的创作领域。

## 核心能力

- **人格化编辑部**：11 位 Agent 各自有姓名、性格、说话风格、价值观、情绪基线、弱点与盲区、人际预设、激励源；日常/日记/周记/会议/消息/认领六套模式，前端可直接编辑并部署。
- **工作日节拍**：开工 = 上班（晨会 → 主产出 → 决策点），收工 = 下班；主产出结束后由你决定收工、开会或继续补跑。
- **会议系统**：轮次模式（主席点将、六段发言、报告落盘）与自由讨论模式（事件驱动自主接话、@指定必答、沉默权、冷场推进、审批弹窗）并存，九类会议按类型路由材料与会后动作。
- **协作与记忆**：agent 间消息流（会话视图）、行动项认领、每日日记、周会前周记、观点演化时间线、关系（信任/摩擦/熟悉度）随协作自动更新。
- **知识体系**：通用写作知识包（工具式按需调用）、经验卡草案（会议蒸馏 + 人工采纳）、每书设定库（版本化，防吃书）。
- **平台发布**：番茄作者后台 HTTP 发布，封面提示词、自动建书/绑定、AI 声明、失败留痕与补发。
- **桌面控制台**：React 面板 + Electron 原生窗口（托盘、通知、开机自启），SSE 实时推送 + 轮询双通道。

## 核心指标

| 指标 | 数值 |
| --- | --- |
| Agent 数量 | 11 |
| 会议类型 | 9 类 × 2 种模式（轮次 / 自由讨论） |
| 后端测试 | 578 个 unittest（数量以 `python run_tests.py` 输出为准） |
| 前端测试 | 45 个 Vitest（数量以 `cd webapp && npm test` 输出为准） |
| 月预算 | 默认 ¥100（设置可调，超限熔断） |

## 编辑部的一天

1. **开工**（手动为主）：首页指令行选择写稿 N 章 / 整理日 / 开会日 / 自由安排，可附老板指令。
2. **晨会**：掌印分派，行动项落任务板。
3. **主产出**（写稿日）：A/B 双轨并行——大纲 → 写稿 → 润色 → 逻辑审稿 → 读者审稿 → 主编终审 → 质量门 → 发布；单轨失败只短路该轨，次日可补。
4. **决策点**：主产出完成，等老板选择收工、开会或继续补跑。
5. **收工**：全员日记（含心情）、知识同步、行动项回填，状态落 `daily_runs`。

## 编辑部成员（11 位）

| 人格 | 文件 | 角色 |
| --- | --- | --- |
| 文策 | planner.md | 选题策划、大纲与卷目标 |
| 守界 | guard.md | 世界观守护：OOC / 吃书 / 伏笔矛盾拦截 |
| 墨白 | writer.md | 正文初稿（A/B 共用） |
| 润物 | editor.md | 去 AI 味、文本质感 |
| 守正 | reviewer.md | 逻辑审稿：六类底线问题 |
| 阿读 | reader.md | 读者视角审稿：追读欲 / 钩子 / 情绪 |
| 掌印 | eic.md | 主编：分派、仲裁、会议主席 |
| 录事 | memory.md | 摘要、角色状态、事件、伏笔台账 |
| 书案 | work_meta.md | 书名、简介、标签、主角、卷目标 |
| 终局 | ending_judge.md | 完结评估：进度、伏笔回收、收尾建议 |
| 博闻 | knowledge_keeper.md | 知识库策展：维护知识包、整合经验卡、审查热点 |

前端 Agent 管理页支持自定义显示名、头像文字、头像颜色与头像图片（本机生效，可导出/导入 JSON 备份），并可编辑人格档案、模型、温度后保存部署。

## 协作机制

- **消息流**：agent 之间横向消息（审稿打回、提案、议题、便签），按主题线程聚合为会话视图，未读优先，可按类型/编辑/关键词筛选。
- **行动项**：会议产出与日常任务落 `agent_actions`，可认领、兑现检查。
- **两级记忆**：每日日记（`what_done / observations / feelings / concerns / thoughts`）、周会前周记（参考上周形成连续记忆）、心情随日记更新。
- **关系**：反馈打回 → 摩擦上升；提案采纳 → 信任上升；协作累积 → 熟悉度上升；数值封顶并带衰减。
- **留痕**：全量事件进 `audit_logs`，面板「留痕档案」可筛选回看。

## 会议系统

- **轮次模式（周会/专题）**：主席点将 → 三轮通气（先回应他人再发言）→ 主席总结报告 → 蒸馏经验 → 落盘决策。发言六段结构：本周小结 → 感受 → 意见 → 顾虑 → 提案 → 优先级。
- **自由讨论模式**：事件驱动自主发言——无需点名，编辑按「话题 × 个人关注点」自主接话、有权沉默（输出 `speak:false`）、可主动抛议题；老板可 `@名字` 指定必答、随时插话；冷场由编辑主动推进或主席拉回；agent 请求拍板时面板弹审批卡（同意/拒绝/暂缓，超时自动过期）；长历史自动压缩为摘要锚点并广播压缩状态。
- **九类会议**：编辑部例会、剧情碰头会、选题会、单章会诊、数据复盘会、收尾会、危机处理会、知识分享会、茶水间闲聊。材料、议程、会后动作按类型路由。
- **实时性**：自由会议消息落 `meeting_messages`（增量 + 索引），SSE 推送直播（消息/思考状态/审批/压缩事件），断线自动重连并拉全量补齐。

## 创作链路（主产出）

写稿日主产出：预检（Cookie/预算/锁）→ 分派 → 晨会 → 大纲 → A/B 双轨（写稿 → 润色 → 审稿 → 读者审 → 终审 → 质量门）→ 发布 → 归档 → 日记 → 知识同步 → 收工。链路拓扑在面板「链路」页可视化（React Flow + 状态着色 + 离线 HTML 导出）。

## 知识体系

- **通用知识包**：`prompts/knowledge/` 下 6 个写作知识包（开篇钩子、节奏爽点、人设关系、巧思伏笔、去 AI 味、市场选题），agent 按需工具式调用（`get_knowledge`），长文不常驻。
- **每书设定库**：`novel_knowledge` 版本化存储世界观、角色、规则，随剧情推进更新，agent 写作/审稿时读取防吃书。
- **经验卡**：会议蒸馏与知识管家产出 `knowledge_drafts` 草案，前端预览、编辑、采纳（写入知识包并重新部署）、拒绝。

## 平台发布（番茄）

发布走番茄作者后台 HTTP 接口：`publish_stock` 发布、`create_book` 建书、`check_stock` 存稿判定、`get_meta` 元数据、`collect_reader_stats` 阅读数据采集。发布日志留痕 `publish_logs`，失败可补发；登录态过期有预检提示与告警。

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
| agent_actions / agent_activity | 行动项 + 活动日志 |
| daily_runs | 工作日状态机与运行留痕 |
| weekly_meetings / meeting_sessions | 会议档案 + 状态机（rounds/free、摘要锚点） |
| meeting_messages / pending_interactions | 自由会议消息流 + 审批/澄清待办 |
| knowledge_drafts | 经验卡/知识包更新草案 |
| audit_logs | 全量留痕 |

## 面板与桌面

React + Vite + Tailwind 面板，Electron 原生窗口（托盘常驻、关窗隐藏、执行通知、开机自启），双主题（亮/暗）完整 token 体系。五区两级导航：

| 区 | 页面 | 内容 |
| --- | --- | --- |
| 总览 | 仪表盘 | 状态带、开工指令行、今日记录、行动项、待您决定、本月、热点 |
| 编辑部 | 消息流 | 会话视图（线程聚合、未读优先、筛选） |
| 编辑部 | Agent 管理 | 人格编辑/部署、日记周记、自定义头像与导出导入 |
| 编辑部 | 会议中心 | 轮次/自由讨论、SSE 直播、@指定、审批弹窗、档案 |
| 创作 | 作品库 / 章节管理 / 阅读数据 | 设定、章节表格 + 正文预览、完读率趋势 |
| 运营 | 成本中心 / 执行记录 / 链路 | 预算、运行留痕、拓扑可视化 |
| 系统 | 系统设置 / 留痕档案 | 运行开关、预算模型、全量审计 |

## 快速开始

### 环境要求

- Python 3.9+（项目在 3.11 验证）
- Node.js 18+（前端构建）
- 番茄作者账号（已实名）
- DeepSeek API Key

### 安装

```bash
cd novel-editorial
python -m pip install -e .          # 或用 uv
cd webapp && npm install && npm run build
cd ../desktop && npm install
```

### 配置

把 `.env.example` 复制为运行环境可读的 `.env` 并填写：

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` | 番茄作者后台登录态（约 1–2 个月失效） |
| `FANQIE_BOOK_ID` | 番茄作品 ID（面板绑定可自动写入） |
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

### 开工与开会

- 首页指令行：选模式（写稿/整理日/开会日/自由安排）→ 选章数 → 附老板指令 → 开工。
- 会议中心：填主题 → 选类型 → 选「轮次」或「自由讨论」→ 发起；自由讨论里输入 `@名字` 指定必答，出现审批卡直接拍板，`结束并总结` 落盘。
- 命令行演练：`python tools/workday.py --action open --mode write --dry-run`。

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
│   ├── web_api.py           # HTTP + SSE 路由壳（业务在 services/）
│   └── services/            # control / dashboard / meeting_session / agency / knowledge ...
├── prompts/
│   ├── agents/              # 11 位人格化 Agent（人物档案 + 六套模式）
│   └── knowledge/           # 6 个通用写作知识包
├── tools/
│   ├── workday.py / editorial_daily.py        # 工作日状态机与主产出调度
│   ├── agent_meeting.py / meeting_kinds.py / meeting_materials.py / meeting_actions.py  # 轮次会议
│   ├── meeting_free_loop.py / meeting_executor.py / meeting_speaker.py  # 自由会议调度（事件驱动）
│   ├── meeting_mentions.py / meeting_interactions.py / meeting_events.py  # @路由 / 审批 / SSE 广播
│   ├── agent_tool_loop.py / agent_context.py / mailroom.py / relations.py / agency.py   # 协作
│   ├── novel_knowledge.py / knowledge_keeper.py / distill_lessons.py  # 知识体系
│   ├── preflight.py / check_stock.py / publish_stock.py / record_work.py ...   # 发布链
│   └── release_lock.py      # 异常残留锁释放
├── webapp/                  # React + Vite + Tailwind 前端（Vitest，五区导航 + 双主题）
├── desktop/                 # Electron 壳
├── n8n/                     # 遗留工作流 JSON（回退备份，已退役）
├── scripts/                 # 安装/自启/发布辅助脚本
├── docs/                    # planning / reviews / evolution / design
├── tests/                   # 578 个后端测试（unittest）
└── demo.db                  # 运行数据库（gitignore）
```

## 文档地图

- `docs/planning/`：决策记录、工程表、评估报告、验收清单
- `docs/reviews/`：审查报告与轮次归档（`rounds/` + `legacy-tracker.md`）
- `docs/evolution.md`：迭代演进记录
- `docs/design/`：UI 概念稿与截图

## 已知限制与风险

- 番茄登录态约 1–2 个月失效，需重新注入 Cookie；发布频率与字数受平台风控约束。
- LLM 输出受模型能力限制：自由会议的接话自然度依赖相关性预筛质量，自动跑题检测与 LLM 级预筛列为后续升级项。
- 自由会议成本受单会议调用/费用熔断保护（默认 300 次调用或 ¥20），可在系统设置调整。
- 遗留项（日更假绿灯、发布脚本版本提交等）登记在 `docs/reviews/rounds/legacy-tracker.md`，按轮次跟进。

## 开发约定

开发按 `engineering-playbook` skill 执行：四门质量门（DECIDE/BUILD/VERIFY/POLISH）、步级五轴自审、阶段独立审查（P0/P1 清零）、收尾分片全库审查与轮次归档；测试一律临时库 + mock LLM，不触真实外部系统。
