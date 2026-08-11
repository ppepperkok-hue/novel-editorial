# 流水线进化机制（2026-08-10）

流水线的可持续性靠三条：**提示词资产化**、**配置驱动生成**、**数据反馈回路**。
改写作风格、调整模型、加一个 Agent，都不需要再手改 66KB 的工作流 JSON。

## 1. Agent 提示词资产化

15 个 LLM 节点的 system prompt 抽到了 `prompts/agents/*.md`，每个文件带
frontmatter（model / temperature），正文即系统提示词：

```text
prompts/agents/
  planner.md      策划官（出大纲/圣经）
  guard.md        世界观守护
  writer.md       叙事写手（A/B 共用）
  editor.md       文字编辑（A/B 共用）
  reviewer.md     逻辑审稿（A/B 共用）
  reader.md       读者体验审稿（A/B 共用）
  eic.md          主编终审（A/B 共用）
  memory.md       记忆官（A/B 共用）
  work_meta.md    作品资料
```

写手/编辑提示词里的动态字数用 `{TARGET_WORDS}` 占位符表示，渲染时展开为
n8n 表达式，实际值由控制台「目标字数」设置决定。

## 0. Agent 成长系统（2026-08-10 升级）

流水线现在是真正会成长的：知识按需调用、经验可沉淀、热点自动更新。

- **工具式知识调用**：`prompts/knowledge/*.md` 是知识库（frontmatter 含
  agents/type/keywords），长知识包不常驻提示词。n8n 的 15 个 LLM 节点全部
  改为调用本地 `POST /api/agent/run`，`tools/agent_tool_loop.py` 实现标准
  function calling 循环：首轮带 `get_knowledge` 工具声明（不传 tool_choice，
  兼容 DeepSeek V4 thinking 模式），模型自主发 `tool_calls`，本地检索知识包
  并以 `role:"tool"` 回传，二轮输出最终结果；无工具调用则单轮。
- **第 11 位 Agent「博闻」**：`prompts/agents/knowledge_keeper.md`，知识库
  策展人。每天 03:30 由 n8n 工作流「知识管家维护」触发
  `tools/knowledge_keeper.py`：市场类知识包自动更新，技巧/规则类与经验整合
  落 `knowledge_drafts` 草案，人工在前端一键采纳后写入知识库并重新部署。
- **反思蒸馏**：周会结束后自动跑 `tools/distill_lessons.py`，从会议记录、
  本周日记、质量与读者数据蒸馏经验卡（草稿）；专题会议可手动触发。前端
  Agent 管理页可预览/编辑/采纳/拒绝，采纳即写知识包并 render+deploy。
- **热点双轨采集**：`novel_pipeline/hot_topics.py` 先 HTML 直抓，失败或空
  时降级 bb-browser（每次重新 open，eval 提取书名并清洗字体乱码）；首页
  「热点选题」有「立即采集」按钮，日更/周会/选题会材料均注入热点数据。

## 2. 配置驱动生成（进化闭环）

```bash
# 改提示词：编辑 prompts/agents/xxx.md（含 model/temperature）
# 渲染回工作流：
python tools/render_workflow.py
# 深度校验（JS 语法 / 节点引用 / 连线）：
node tools/validate_workflow_deep.mjs
# 推送到 n8n（见 n8n/README.md 的 API key 用法）
```

反向导出（把工作流里的最新提示词同步回资产文件）：

```bash
python tools/export_agent_prompts.py
```

加一个新 Agent 的步骤：在 `n8n/novel_workflow.json` 增加节点后跑一次导出，
再把新节点加入 `AGENT_FILES` 映射；以后该 Agent 的进化全部走资产文件。

## 3. 数据反馈回路

- 每章发布后 `collect_reader_stats.py` 拉取番茄完读率/追读率 → CSV → 前端图表。
- `get_meta.py` 把低完读率章节、平均完读/追读率打包成 `reader_feedback`，
  注入次日记忆包，写手/审稿/架构师都能看到读者反应。
- 架构师周会消费完读率与热点，输出蓝图增量与卷目标调整。
- 成本台账（cost_logs）+ 预算熔断（preflight）防止失控扩张。

## 4. 前端工程化

监控面板已从单文件 HTML 升级为 React + Vite + Tailwind 工程（`webapp/`）：

```bash
cd webapp
npm install
npm run build        # 产物 webapp/dist，由 web_api 自动托管
npm run dev          # 本地开发热更新
```

`novel_pipeline/web_api.py` 优先服务 `webapp/dist`，不存在时回退旧版
`web/index.html`。桌面控制台（`python -m novel_pipeline.desktop`）复用同一前端。

## 5. 可调设置（控制台）

`settings` 表（tools/app_settings.py）：

| key | 默认 | 消费方 |
| --- | --- | --- |
| daily_enabled | true | preflight（熔断开关） |
| monthly_budget | 100 | preflight（预算熔断） |
| target_words | 2000 | 写手/编辑/质量门（动态字数） |
| style_tweak | 空 | 记忆包风格微调 |
| manual_run_requested | 0 | preflight（请求下次触发运行） |

## 6. 桌面管理面板 v2（2026-08-10）

监控面板重构为多分区桌面管理软件（pywebview 原生窗口内运行 React），
侧边栏导航 + 顶部状态栏，共 8 个分区：

| 分区 | 内容 |
| --- | --- |
| 仪表盘 | 9 项 KPI、工作流启停、预算进度、健康检查、热点选题、完读率、发布日志 |
| 作品库 | 大纲/主角/角色卡/人物关系/世界观/卷目标/伏笔台账，逐书展开 |
| 章节管理 | 状态筛选（草稿/审稿/待发布/已发布）、字数/评分/修订、章纲详情 |
| Agent 管理 | 9 个智能体卡片 + 提示词编辑器 + 模型/温度，保存→渲染→校验→部署到 n8n |
| 成本中心 | 日成本柱状图、按节点 Token/费用表、预算进度 |
| 执行记录 | 日更/周会最近 30 次执行状态与耗时 |
| 阅读数据 | 完读率/追读率趋势、逐章数据表、低表现章节反馈 |
| 系统设置 | 日更开关、预算、目标字数、风格微调、架构说明 |

Agent 管理链路：`prompts/agents/*.md` → 保存时 `render_workflow.py` 重渲染
`n8n/novel_workflow.json` → `tools/validate_workflow_deep.mjs` 深度校验 →
面板内一键 PUT 到 n8n 日更工作流。校验脚本已移出 `tools/archive/`（该目录
不进 git），改为仓库跟踪的 `tools/validate_workflow_deep.mjs`，路径按脚本
自身位置解析，clone 后即可用。

新增 API：`GET/POST /api/agents`（列表/保存/部署）、`GET /api/cost`、
`GET /api/executions`。前端支持 `#分区` hash 直达，刷新后停留在当前页。

## 7. 手动补更与更新时间（2026-08-10）

机器会关机，定时触发可能错过，因此给两个工作流各加了一个 Webhook 触发节点：

| 工作流 | Webhook 路径 | 入口 |
| --- | --- | --- |
| 日更 | `POST /webhook/novel-manual-run` | 手动触发 → 备份数据库 → 预检 → … |
| 周会 | `POST /webhook/novel-weekly-run` | 手动触发 → 读上下文 → 架构师规划 → … |

面板「系统设置」的「立即更新一章 / 立即跑周会」直接打这两个 webhook；
「每日更新时间」修改 `n8n/novel_workflow.json` 的 schedule trigger 后重新部署。

本轮同时修掉了三个让流水线在 Windows 上断掉的问题：

- **python 不在 PATH**：所有 ExecuteCommand 的 `python` 曾换成
  `C:/Users/.../Python311/python.exe` 绝对路径；2026-08-10 二审已改为
  `$env.PYTHON_EXE` / `$env.PIPELINE_ROOT` 参数化，不再硬编码机器路径。
- **cwd 漂移**：n8n 进程工作目录是 `~/.n8n`，所有相对脚本路径改为绝对路径；
  大 payload（周会蓝图/日更结果）不再走命令行（超过 cmd.exe 8191 字符限制），
  改为 code 节点写 `n8n_tmp/*.json`，Python 端用 `--file` 读取。
- **Code 节点模块限制**：`~/.n8n/.env` 增加 `NODE_FUNCTION_ALLOW_BUILTIN=fs`。

开机自启：`shell:startup` 下放了三个 vbs（n8n、8000 面板服务），
登录后自动拉起，无需管理员权限。

## 8. 前端高完成度与后端健壮性（2026-08-10）

面板交互升级：侧边栏可折叠（状态记忆）、Ctrl+R 刷新、首次加载骨架屏、
页面级错误边界、危险操作确认对话框（补更/暂停/部署/切 Agent 丢修改）、
Toast 带图标、执行失败可查看原因弹窗、作品库搜索与批量展开、
章节统计卡、设置表单前端校验、刷新/时间显示、AstrBot 深色主题统一。

后端修复三个真实缺陷：

- `_agent_save` 的子进程输出用 `errors="replace"`，避免中文输出在
  Windows 管道编码下抛 UnicodeDecodeError。
- `_executions` 为失败执行附加错误摘要（n8n `includeData`，60 秒缓存），
  前端执行记录页可直接看到失败节点与原因。
- 日更并发锁：`tools/preflight.py` 预检通过时原子创建
  `n8n_tmp/daily.lock`（O_EXCL），阻止定时与手动触发同时通过预检导致双发；
  正常路径（采集阅读数据）与失败路径（结束）都会释放，PID 失效自动回收；
  `tools/release_lock.py` 可手动释放。

另修复 `tools/apply_architect.py` 的 `volume_goal` 查询缺字段问题
（蓝图不带卷目标时崩溃），SQL 改为显式选取 `volume_goal`。

## 9. 桌面壳稳定化（2026-08-10）

此前尝试 pywebview 无边框窗口 + 自绘标题栏 + 手动拖动，在 WebView2 上
不稳定（CSS app-region 不生效、手动 move 高频调用、窗口偶发退出）。
已整体重写为稳定方案：

- 恢复系统窗口边框：拖动、缩放、关闭全部由 Windows 原生处理。
- 深色标题栏/边框/文字：窗口就绪回调（UI 线程）里通过 DWM
  `DWMWA_USE_IMMERSIVE_DARK_MODE`（20/19）+ Win11 的边框/标题/文字色
  属性（34/35/36）设置为 `#1a1a1a` 深色，消除白框。
- 移除前端自定义窗口控制按钮与拖动逻辑；`index.html` 内联深色背景 +
  `color-scheme: dark`，页面加载瞬间也不白闪。
- 原生控件（select 下拉、time picker、autofill、number spinner）全部深色化。

注意：Windows 浅色主题下窗口边缘仍有系统阴影光晕，开启系统深色模式后
完全消失；面板本身在任何主题下都是深色。

## 10. Electron 桌面壳（2026-08-10）

为获得真正的现代软件窗口体验（无系统标题栏、自绘深色标题栏、圆角），
桌面壳从 pywebview 切换到 Electron（与 Codex 桌面同类引擎）：

- `desktop/main.js`：frameless 窗口（1320x880），启动时自动拉起
  `pythonw -m novel_pipeline.web_api`（8000 被占用则复用），窗口关闭时
  回收自起的 API 进程；IPC 处理最小化/最大化/关闭。
- `desktop/preload.js`：`contextBridge` 暴露 `window.desktopApi`。
- 前端在 Electron 环境渲染 42px 自绘标题栏（`app-region: drag` 拖动 +
  品牌区 + 最小化/最大化/关闭按钮），浏览器访问时自动隐藏。
- `launch_desktop.vbs` 启动器 + 桌面快捷方式（wscript → vbs → electron）。

开发运行：`cd desktop && npm install && npm start`；
安装依赖使用 `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`。
`novel_pipeline/desktop.py`（pywebview 版）保留作后备入口。

## 11. v2.0 大版本（2026-08-10）

- 双主题：CSS 变量令牌化（深色/浅色），跟随系统 + 手动切换（设置页/命令面板），
  持久化到 localStorage，URL `?theme=dark|light` 可强制。
- 命令面板：`Ctrl+K` 呼出，模糊搜索页面/刷新/立即更新/暂停恢复/主题切换，
  键盘上下选择、回车执行、Esc 关闭。
- 章节阅读器：正文落库 `chapter_content`（n8n 汇总节点携带正文 →
  `record_work.py` 写入），`GET /api/chapter_content?chapter_id=`，
  章节页「阅读」按钮打开弹窗，支持字号调节。
- 实时推送：`GET /api/events`（SSE，5 秒快照：工作流状态/最近执行/健康/成本），
  前端保留轮询降级。
- Electron 桌面集成：托盘（显示/隐藏/立即更新/周会/退出）、执行完成系统通知、
  单实例锁、关闭窗口最小化到托盘、设置页开机自启开关与退出按钮。
- 工程化：electron-builder NSIS 安装包（带图标），安装版从
  `resources/novel-pipeline` 运行 API、数据库放 `%APPDATA%`；
  electron-updater 对接 GitHub Releases 自动更新；前端 Vitest 冒烟测试。

安装包构建：`cd desktop && npm run dist`，产物在 `desktop/release/`。
发布新版本：打 tag（如 v1.0.0）后构建并 `--publish always` 上传 GitHub Releases。

## 12. 人格化多 Agent 周会系统（2026-08-10）

周会从单 Agent 规划升级为多 Agent 会议制，全部 10 个 Agent 人格化：

- **人格档案**：每个 `prompts/agents/*.md` 增加人物档案（姓名/身份/性格/说话风格/
  价值观/关注点/情绪基线）与「日记模式」「周记模式」「会议模式」，日常任务不变。
- **两级记忆**：日更后「全员写日记」节点让每个 Agent 自述当日日记
  （`agent_diaries`，daily）；周会前每个 Agent 回顾本周日记与简报写「本周日记」
  （weekly），参考上周周记形成连续记忆；保留 8 周自动清理。
- **情绪状态**：周记同一次调用自述心情 `{satisfaction, concern, excitement, fatigue}`
  写入 `agent_states`；会议发言带「我的感受」。
- **会议引擎** `tools/agent_meeting.py`：主席（eic）点将（动态阵容≤8）→ 固定 3 轮
  相互通气（每 Agent 上下文 = 材料 + 本人简报 + 本周日记 + 心情 + 历史发言）→
  主席总结报告；发言六段结构 `本周小结→感受→意见→顾虑→提案→优先级`。
- **周会材料** `architect_weekly.py` 输出 context（20 字段）+ 每个 Agent 的
  `agent_briefs`（本周数据聚合）。
- **落盘与档案**：`apply_architect.apply_report` 合并蓝图/读者画像/卷目标；
  `weekly_meetings` 表存档完整会议；前端新增「周会档案」页（导航第 9 项）+ 仪表盘
  最近周会摘要；`GET /api/meetings`。
- **成本**：日记与会议调用按 Agent 记入 `cost_logs`（node_name `日记:*` / `会议:*`）。

后续待办（完成后提醒）：完结机制（ending_judge 接入点将）、统一留痕
（`audit_logs`）、人物卡进化（`character_evolution`）。

## 13. 自动建书与封面提示词（2026-08-10）

- **一键自动建书** `tools/create_book.py`：新书确认后作品库页「一键自动建书」，
  复用发布链路同款 Cookie + CSRF 鉴权，自动拉分类/标签列表匹配（genre+tags 字符匹配，
  fallback 前两条），简介单行化并补齐 50 字，主角名清洗去括号/别名并截 5 字，
  调 `book/create/v0/` 建书 → `volume_list/v1/` 取卷 → 复用 `ending.bind_book`
  落库并写 `~/.n8n/.env`，状态 ready → publishing；audit 记 create_book 详情。
- **平台限制**：番茄每天最多创建 1 本新书；失败当天无法重试，错误信息已带提示。
- **封面提示词**：会议主席总结报告新增 `cover_prompt` 字段（画面主体/风格/色调/构图/
  文字排版），`apply_architect` 落盘到 `novels.cover_prompt`（新书创建时随书携带），
  专题会议结束后也统一调 `apply_report` 落盘；作品库新书卡片与会议结论均可复制提示词，
  用户用豆包出图后自行上传番茄封面。
- **前端**：作品库 ready 卡片主按钮「一键自动建书」+ 状态文案，「手动绑定」收进折叠备用；
  会议中心结论区展示封面提示词（带复制按钮）。
- **验证**：新增 `tests/test_create_book.py`（10 例：gender/清洗/补齐/匹配/全链路绑定/
  状态拒绝/已绑定拒绝/缺 Cookie/平台拒绝）；apply_report 封面落盘与不清空、随新书携带
  测试；全量 104 后端测试 + 6 前端测试 + 构建通过。

## 14. README 全面重写（2026-08-10）

- 逐个模块过完整个项目（n8n 三套工作流 61/7/4 节点、11 位 Agent、知识体系、热点双轨、
  会议系统、自动建书、数据层 21 张表、监控测算、前端与 Electron、测试部署），
  README 从约 150 行扩到 490+ 行。
- 结构：核心指标 → 架构总览 → 快速开始 → 日更流水线逐阶段解析（触发预检/记忆包/
  A/B 生成/发布/沉淀）→ 多 Agent 系统 → 知识体系与成长闭环 → 热点采集 → 会议系统 →
  自动建书与封面 → 数据层 → 监控告警经济模型 → 前端桌面 → 安全加固 → 目录结构 →
  开发测试部署 → 已知限制 → 后续路线。
- 每个功能都写明「实现方式（模块/文件/机制）」与「发挥效果（数据流/作用）」，并附
  命令示例与关键参数（工作流 ID、端口、阈值、单价、番茄接口路径）。
- 自检：Markdown 围栏配对、目录锚点与章节一致、关键数字（节点数/Agent 数/知识包数/
  测试数/分类数）逐项对照代码核对。

## 15. 严格审查清单逐条修复（2026-08-10）

按外部审查清单（23 项）逐条修复，全部阻断级/高危项落地并实测：

- **日更链路**：B 轨接线修复（整理剧情B → 排版B 直连，同步设定知识库移到收尾）；
  novels 补 volume_id 列（publish_stock 不再查空列）；端口统一 8000（render 无条件
  重写 agent 节点 URL，并注入可选 PANEL_TOKEN 头）；直发成功章节落库 status='published'
  （幂等护栏恢复，收尾发布存稿不再捞已发章节）。
- **executeCommand 参数模型**：三份工作流全部改为 `command + commandArguments + cwd`，
  解释器/项目根走 `$env.PYTHON_EXE` / `$env.PIPELINE_ROOT`（已写入 ~/.n8n/.env），
  去除 `&` 与硬编码路径；get_meta/record_work ROOT 相对化，launch_desktop.vbs 相对化。
- **成本记账**：/api/agent/run 返回 usage；日记/会议/知识管家/蒸馏按模型单价折算
  （estimate_cost）；cost_logs 加 run_id 幂等去重；会议按 Agent frontmatter 选模型。
- **预检与监控**：手动补更请求失败不再被吞（成功才清零）；Windows 锁检测改用
  OpenProcess/GetExitCodeProcess（不再可能杀进程）；发布失败计数统一 7 天窗口；
  面板预算改读 settings 表（与熔断同源）。
- **安全**：web_api 强制 127.0.0.1、Origin 本机校验、POST 拒 text/plain、可选
  PANEL_TOKEN；知识包读写路径穿越防护；静态服务 CORS 收紧；快照线程异常落 alerts.log。
- **数据一致性**：demo.db 写死穿透修复（会议会话、agent 工具、check_stock 支持
  实际 db 路径）；record_work 角色 upsert 保留配角、伏笔回收精确匹配、成本幂等；
  建书标签改为词级匹配 + 交集打分；题材闭环（设置/环境变量 → check_stock → 设定题材），
  解析大纲拒绝静默兜底（缺章纲直接报错）。
- **工程质量**：LLM 配置统一（进程优先/.env 兜底）、chat_deepseek 加重试、空 content
  报错；n8n 服务空 key 不缓存、错误缓存限容；SQLite 单次建表迁移 + WAL + 外键 + 索引；
  桌面 pythonw 路径可配置；文档数字统一（61/7/4/116/11）、「已跑通」宣称修正。
- **校验与测试**：validate_workflow_deep 升级为数据流语义校验（排版上游、发布链、
  收尾链、executeCommand 参数化、端口统一）；新增 publish_stock/preflight 守卫/
  record_work/check_stock/control/misc/n8n 服务/鉴权/路径穿越测试，全量 120 后端 +
  6 前端全绿；三份工作流已推送到 n8n 并保持激活。

## 16. 二审清单修复（2026-08-10，提交后对账）

按二审清单（P0-P3）继续修复：

- **P0 双解释器**：所有 executeCommand 的 commandArguments 首元素误带
  `$env.PYTHON_EXE`（command 已是解释器，等于让 Python 解析 python.exe），
  已全部移除；validator 新增「args 不得重复解释器」检查。
- **P1 汇总节点路径**：写 `n8n_tmp/daily_result.json` 改用
  `process.env.PIPELINE_ROOT` 拼接，不再硬编码 E 盘；validator 新增 code 节点
  机器路径扫描。
- **P2 收尾链**：存稿充足分支（发布存稿 → 结束）现在接入完整收尾链
  （发布存稿 → 采集阅读数据 → 全员写日记 → 同步设定知识库 → 结束），两条路径
  收尾一致，语义校验同步更新。
- **P2 题材配置**：设置页新增「日更题材 · 核心设定 / 题材 / 关键词」输入框，
  保存写入 settings，经 check_stock 流入设定题材节点，周会选题可真正进入日更。
- **P3 清理**：meeting_session 去掉模块级 `_DB_PATH` 全局（会话表加 db_path 列，
  后台线程按会话读取）；estimate_cost 与 PANEL_TOKEN 加 5 秒环境缓存与数值容错；
  web_api do_POST 异常路径兜底关闭连接；publish_stock 不再 SELECT 冗余 volume_id；
  `Origin: null`（file:// 兜底页）只放行 GET、拒绝 POST；agent_tool_loop 第二轮
  若出现多余 tool_calls 明确标注 ignored；ARCHITECTURE 测试数改 120、evolution
  历史段落清理绝对路径与 8000/8001 字样。
- **验证**：后端 120 + 前端 6 全绿；validate 全工作流通过；三份工作流重新部署
  到 n8n 保持激活；8000/8001 服务重启，鉴权实测 dashboard 200 / 跨站 403。

## 17. 三审报告修复（2026-08-10）

按第三方审查报告（40 项）继续修复，重点：

- **发布状态管理**：汇总运行结果显式记录质量门失败章节（status=draft +
  错误原因落库，publish_logs 可见）；发布失败章节保留 `reviewed` 供存稿池补发；
  scheduler 改用 chapter_content 正文（不再把章纲当正文发）；record_work 不再
  无条件覆盖作品状态（finished 书不会被复活）。
- **安全边界**：agents_save 补路径穿越防护（必须 .md 且位于 AGENTS_DIR 内）；
  web_api token 校验扩展到 GET；POST 请求体上限 5MB；SSE CORS 与其他端点一致；
  500 响应不再向客户端泄露内部异常（写 alerts.log）。
- **监控与成本**：load_alerts 接入真实当月花费与预算（成本超限告警可触发）；
  record_work 单价改读 ~/.n8n/.env；n8n 汇总补「主编终审A/B」成本记账；
  写手/策划 max_tokens 上调（writer 4000 / planner 3000，frontmatter 可配，
  agent_save 保留额外 frontmatter 键）。
- **autopilot 真发布**：FanqieHttpAdapter 实现三步发布（复用 publish_stock）；
  pipeline 生成正文落库 chapter_content；计划任务模式不再只写无人消费的 jsonl。
- **一致性**：create_book 性别判定去掉「穿越」归女频、错误提示精确化；run_demo
  合规门失败不再标 reviewed；会议 20 轮到点自动封顶；agent_meeting 去掉模块级
  全局（materials/topic 参数化），周记统一走 write_diaries；锁文件 30 分钟
  陈旧回收（防 PID 复用卡死）；chat_deepseek 兼容 LLM_BASE_URL/LLM_API_KEY、
  LLMClient 4xx 不重试；ai_taste_check 排比检测按真实位置计数；AI 词表统一到
  `ai_words.json`（Python 与 n8n 质量门同源）。
- **工程**：备份改 sqlite3 backup API（WAL 一致性）；load_env 五处统一到
  config.load_env；静默异常补日志；chapters 唯一索引（novel_id, seq）；
  publish_stock 多书按活跃书发布；pyproject 显式 dependencies；desktop
  package.json 核实为正常 UTF-8（审查误判）；export_agent_prompts 代理模式
  明确提示无需导出。
- **验证**：后端 128 + 前端 6 全绿；validate 全工作流通过；新增质量门失败落库、
  成本告警、agents_save 穿越、导出短路、scheduler 正文、会议库隔离等回归测试。

## 18. 第三轮复查修复（2026-08-10）

按复查报告（A/B/C/D 段）修复：

- **A1 面板回归**：PANEL_TOKEN 的 Bearer 检查恢复为只要求「POST 且无 Origin」，
  GET 与浏览器请求不再被挡（面板可正常打开），文档明确本机信任模型。
- **A2 迁移破坏性**：chapters 去重改为保留「已发布」行优先，删除前先清理
  publish_logs/quality_reports/chapter_content/chapter_summaries 子表引用，
  不再静默删已发布章节、不再留孤儿。
- **A3 锁阈值**：日更锁陈旧回收从 30 分钟放宽到 2 小时（一次日更 15+ 次
  LLM 调用可能超过半小时），防误删活锁导致双发。
- **B1 质量门B**：质量门B 不再 throw（改为返回 passed:false 失败对象），并补齐
  与 A 轨一致的读者/主编仲裁逻辑；validator 增加 `qb.passed === false` 断言。
- **B2 发布日志**：FanqieHttpAdapter 成功/失败都写 publish_logs；
  Scheduler.tick 加 try/except，失败进 report.failures 并走告警，不再裸崩。
- **B3 无正文短路**：scheduler 去掉 COALESCE(cc.content, outline) 兜底，
  reviewed 章节缺正文直接跳过并告警，禁止把章纲发到线上。
- **B4 周记简报**：write_diaries weekly 模式注入每位 Agent 的本周简报
  （materials.agent_briefs），周记上下文恢复完整。
- **B5/B6/B7**：README 测试数 128、代理字段补 max_tokens；质量门词表改
  fs.readFileSync（不再吃 require 进程缓存），fallback 为完整内置词表；
  LLMClient 对 429/5xx 重试、其余 4xx 直接失败。
- **D 段轻量项**：publish_stock 三步发布后 best-effort 复核 chapter_list/v1；
  hot_topics.parse_rank_html 删除死参数；quality_gate 衔接不匹配从 6 分降到
  4 分（低于通过线，真实拦截）；n8n_api 失败限频写 alerts.log。
- **验证**：后端 134 + 前端 6 全绿；validate 全工作流通过；三份工作流重新部署
  激活；服务重启后 dashboard 200 / 跨站 POST 403。

## 19. 第四轮复查修复（2026-08-10，F1-F5）

- **F1 迁移孤儿**：chapters 去重清理扩展到 world_events / character_evolution
  两张子表，测试断言全部子表无孤儿。
- **F2 复核告警**：publish_stock 复核「未在章节列表找到」的警告不再被吞——
  main 与 FanqieHttpAdapter 都写 alerts.log 并透传到返回值（warnings /
  warning 字段）。
- **F3 报告语义**：Scheduler.tick 失败章节只进 failures，不再同时混入
  published（新增回归测试）。
- **F4 双轨失败兜底**：新增「合并兜底」code 节点（整理剧情A → 合并兜底 →
  合并发布结果）：校验发布A/B 都无输出时输出 failed_both 占位，保证双轨
  同时失败时汇总运行结果仍执行、daily_result.json 照常生成（质量门失败
  章节落库留痕）；直发成功时兜底返回空数组不干扰原链路；validator 增加
  兜底连接断言。
- **F5 SQLite 兼容**：去重 SQL 改用相关 EXISTS 写法（不再依赖 ROW_NUMBER
  窗口函数），SQLite < 3.25 也可运行，且修正了「同状态最小 id」保留语义。
- **验证**：后端 136 + 前端 6 全绿；README/ARCHITECTURE 测试数同步为 136；
  三份工作流重新部署激活。

## 20. 初始知识库与逻辑一致性审查（2026-08-10）

- **bible → 设定知识库初始化**：新增 `novel_knowledge.sync_from_bible`——
  Planner 首轮故事圣经自动初始化 world_rule/character/plot/item/power 分类
  （世界规则、角色卡、人物关系、金手指、主线、文风），内容未变化不重复版本化；
  日更工作流在「解析大纲」后新增「初始化设定知识库」节点（63 节点），收尾
  `sync-latest` 兜底补跑；validator 增加初始化链断言。
- **autopilot 双发防护**：计划任务模式与 n8n 日更共享同一把 `daily.lock`
  （复用 preflight 锁），锁占用时直接跳过并返回原因，不再可能双发。
- **n8n 主链路质量统计**：汇总运行结果为每章携带 `quality_passed`，
  record_work 写入 quality_reports——仪表盘质量指标不再恒零。
- **审查确认的一致性项**：番茄侧书名/简介判断基于 book_list 实况；知识包在
  代理模式下本地读取无需部署；章节唯一索引与子表清理；成本预算三处同源；
  前端章数上限与后端一致。
- **文档化边界**：番茄已发布但本地汇总中断的边缘不一致、n8n 固定 demo.db 的
  路径约定、8001 兼容实例说明，均写入 README 已知限制。
- **验证**：后端 141 + 前端 6 全绿；validate 全工作流通过；新增 bible 初始化
  幂等/autopilot 锁/质量落库测试。

## 21. 世界观/人物卡链路梳理与审查（2026-08-10）

- **读取盲区修复**：读者审稿/主编终审/提炼剧情（A/B 共 6 节点）此前不读故事圣经——
  首轮 writing_context 早于 Planner 生成，不含 bible，导致首章 OOC/设定审查盲区；
  现在 6 个节点的 task 统一注入角色卡/人物关系/世界观规则，validator 增加断言。
- **bible 字段补齐**：Planner 提示词新增 `golden_finger`（金手指规则）与
  `main_plot`（主线），sync_from_bible 的 item/power/主线初始化真正有数据可写。
- **防覆盖**：章节增量同步的角色状态实体改为「名字·状态」，不再覆盖 bible 初始化的
  角色卡（人格/口吻/OOC 红线保留），测试同步更新。
- **链路定稿**：定义层（bible，Planner/周会写）、可查设定库（novel_knowledge，
  bible 初始化 + 章节增量 + 前端手动）、动态状态层（characters/evolution，
  record_work 写）三套分工，get_meta 合并；读取时机为「bible 产出后立即初始化、
  写手前可查、收尾增量入库」，已写入 README 6.3。
- **验证**：后端 141 + 前端 6 全绿；validate 全工作流通过；工作流重新部署激活。

## 22. 多书隔离审查与修复（2026-08-10）

- **发现**：Agent 代理调用不携带 novel_id（get_novel_knowledge 以 0 查询设定库，
  设定库形同虚设）；「全员写日记」无 --novel-id 取最新书；周会读上下文/开会
  无书参数取最新书——多书并存时设定、日记、会议材料都会串。
- **修复**：get_meta 输出 novel_id；解析本地资料透传；render_workflow 为全部
  代理节点注入 `novel_id` 表达式；全员写日记绑定 --novel-id；周会两个节点绑定
  `--book-id $env.FANQIE_BOOK_ID`；agent_meeting 支持 --book-id；get_meta
  支持 --db。
- **校验**：validator 增加代理节点 novel_id、日记 --novel-id、周会 --book-id
  断言；新增 get_meta novel_id 与工具 novel_id 透传测试。
- **验证**：后端 143 + 前端 6 全绿；validate 全工作流通过；README 6.3 补充
  多书隔离说明（按书数据表、代理 novel_id、日记/周会绑定、全局数据共享边界）。

## 23. Agent 时序与字段依赖审计（2026-08-10）

- **方法**：静态分析三份工作流——节点级可达性（connections 拓扑 BFS）+
  字段级引用核验（task 引用的上游输出键）。
- **节点级结论**：63 个节点全部引用可达；唯一「不可达」是合并兜底的
  校验发布A/B 引用（try/catch 容错，双轨失败场景设计如此）。周会/知识管家
  全部可达。
- **字段级发现并修复**：`解析本地资料` 未透传 `target_words`——设置页目标
  字数在 n8n 链路恒为 2000；已透传并加 validator 断言。其余字段引用全部
  存在（质量门 editedText 为多分支 return，通过分支确有输出，属审计误报）。
- **各 Agent 读取清单**（供人工核验）：Planner 读解析本地资料（$json 透传）；
  写手/守护/审稿/读者/主编/记忆均读解析大纲 bible + 解析本地资料上下文；
  主编终审额外读两审原始输出；写手B 读整理剧情A 摘要与质量门A 结尾（失败时
  为空串容错）；润色读写手正文与 target_words。
- **验证**：后端 143 + 前端 6 全绿；validate 全工作流通过；工作流重新部署激活。

## 24. 链路审查、前端重构与严谨复查（2026-08-10）

- **链路审查修复**：发现「自动建书/绑定后 n8n 进程不重读 .env」——新增
  `tools/current_book.py` 与「读当前书」节点（64 节点），设定题材的 book_id
  改从数据库读（fallback env），绑定新书后无需重启 n8n 即切换；validator
  增加当前书链路断言与字段透传检查（target_words 等）。
- **前端重构**：`api.js` 统一为 getJSON/postJSON 封装（230 行样板 → 90 行）；
  `App.jsx` 壳层拆到 `components/Shell.jsx`（TitleBar/Sidebar/Topbar/Toasts/
  HelpModal/NAV/PAGE_META），App 从 380 行减到约 230 行，聚焦数据与路由；
  页面组件与文案不变，6 个 Vitest 测试与构建保持全绿。
- **严谨复查**：全量 144 后端 + 6 前端测试通过；validator 全工作流通过；
  三份工作流重新部署激活（64/7/4）；服务重启后鉴权实测正常；README 同步
  64 节点与当前书切换说明。

## 25. 最终全链路走查（2026-08-10）

逐节点提取全部 15 个 Agent 的 task 与提示词日常指令、全部关键 code 节点
（解析/质量门/排版/整理/汇总/校验/复核/兜底）逐对核对，修复三处隐藏问题：

- **润色截断风险**：editor.md 缺 max_tokens，/api/agent/run 兜底 1600 tokens
  可能截断 2000+ 字正文（质量门只数已有字数，截断仍可能达标发布）；
  已加 max_tokens: 4000（A/B 均注入），validator 断言。
- **质量门硬失败**：审稿/读者/主编输出非 JSON 时质量门 extract throw，n8n
  无 error 分支会中断整轮（连健康轨一起停）；改为软失败返回 passed:false
  （失败落库留痕），validator 断言。
- **复核解析崩溃**：番茄复核接口返回非 JSON（反爬/异常页）时解析复核 throw；
  已容错输出 unknown 状态，汇总仍可落库，validator 断言。
- **核对通过项**：15 个 Agent 输出格式与下游解析全部一致（reviewer.passed /
  reader 三字段 / editor.verdict / guard 双字段 / memory 五字段 / planner bible /
  work_meta 六字段）；task 与提示词字段一一对应；多分支 return 的字段（质量门
  editedText）确认通过分支有值、失败分支被空串兜底；合并兜底 try/catch 豁免
  符合设计。
- **验证**：后端 144 + 前端 6 全绿；validator 通过；工作流重新部署激活；
  服务重启后鉴权实测正常。

## 26. 第五轮审查修复（2026-08-10，G1-G10 + P3）

- **P0 表达式语法错误（10 处）**：上轮注入 bible 时把 6 个审阅/提炼节点的
  task 拼接写成 `+'；'章纲：'+`（多引号），写手B/审稿B/生成作品资料结尾
  缺闭合引号，守护细纲末尾多余 `+'`——15 个 LLM 节点 10 个是 JS 语法错误，
  日更会在第一个坏节点失败；已全部修复，`check_expr.js` 校验 15/15 通过，
  validator 增加 jsonBody 表达式语法检查（假绿灯消除）。
- **G4 存稿分支收尾**：全员写日记原引用「解析本地资料」（仅现造分支执行），
  存稿充足分支会因引用未执行节点而失败；改为引用「读当前书」（两条分支都跑）。
- **G5 汇总幂等**：run_id 改用 `$execution.id`（同一执行内多次 merge 输入
  幂等），消除兜底占位导致的成本重复记账。
- **G6 周会当前书**：周会工作流新增「读当前书」节点（8 节点），读上下文/开会
  从数据库取 book_id，不再依赖 n8n 进程环境（绑书后无需重启 n8n）。
- **G7-G10**：record_work 保留 quality_reports 原有详细分数（gate 并入）；
  sync_from_bible 无书时不再写 novel_id=0 孤儿；解析本地资料删除重复的
  「完结状态」；autopilot 默认字数改 2000-2200 并支持 --min-chars/--max-chars，
  install_daily_task.ps1 同步参数。
- **P3**：README/ARCHITECTURE 测试数统一 144；validator 增加表达式语法、
  日记读当前书、周会读当前书断言；current_book.py SELECT 补 id 列。
- **验证**：后端 144 + 前端 6 全绿；15/15 表达式通过；validator 通过；
  三份工作流重新部署激活（64/8/4）；服务重启正常。

## 29. 第八轮审查修复（2026-08-10，J1-J5）

- **J1/J2 失败显式留痕（推翻第七轮 onError 方案）**：n8n 的
  continueRegularOutput 失败时输出空数据、下游不执行，上一轮加容错反而把
  可见报错变成无痕断链。改为 16 个节点（写手/润色/审稿/读者/主编/提炼/整理/
  质量门 A+B）全部 `continueErrorOutput`——失败数据沿 error 分支到新增
  「失败留痕」节点，再喂给合并发布结果；汇总运行结果消费 `llm_fail`，为
  未落库的轨补写 draft+error（publish_logs 可见），无痕丢章从机制上消除。
  合并兜底保留并校验读取质量门A/B 双门；`failed_both` 作为双轨质量门失败的
  触发器，由 qa/qb 分支完成落库。
- **J3 周会重复连接**：读当前书 → 读上下文三条相同边（第六/七轮各加一条），
  会导致周会执行三次烧三倍会议成本；已去重，validator 新增全工作流重复边检查。
- **J4 validator 拓扑断言**：16 节点 continueErrorOutput + error 边指向
  失败留痕、失败留痕喂合并发布结果、汇总消费 llm_fail、合并兜底双门断言、
  重复边检查。
- **J5 README 如实修正**：删除不实「任意 LLM 失败→质量门软失败」表述，改为
  失败留痕机制描述（error 分支 → 失败留痕 → 汇总补 draft+error；A 轨失败时
  B 轨不发布但失败可见；Planner/作品资料失败直接短路）。
- **验证**：后端 144 + 前端 6 全绿；15/15 表达式通过；validator 通过；
  三份工作流重新部署激活（65/8/4）；服务重启正常。

## 30. 第九轮审查修复（2026-08-10，K1-K6）

- **K1 merge 接线**：合并发布结果 numberInputs=4，四条上游（复核A/B、合并兜底、
  失败留痕）分配唯一端口 0-3；validator 校验端口唯一、连续、与 numberInputs 一致。
- **K2/K6 失败覆盖**：失败留痕改用 `$input.all()` 收集全部错误项；汇总对
  「未覆盖的轨」一律补 draft+error（不依赖失败节点归属判断），A 轨失败时 B 轨
  也补「LLM链路失败」记录，双向无痕消除。
- **K3 防御提取**：失败留痕多路径提取节点名（node.node.name / nodeName /
  error.node.name），取不到时标记 unknown 并由汇总兜底补录。
- **K4 守护细纲**：加入 continueErrorOutput + error 边（共享节点失败时两轨
  都显式落库）。
- **K5 建草稿失败**：新建草稿A/B 加入 error 分支；汇总新增「质量门通过但
  草稿创建/发布链中断」分支，质量过了却无记录的场景不再静默。
- **validator**：守护/新建草稿 error 边、失败留痕 all()、merge 端口与
  numberInputs、汇总 failNames 与 gate-gap 断言。
- **验证**：后端 144 + 前端 6 全绿；15/15 表达式通过；validator 通过；
  三份工作流重新部署激活（65/8/4）。

## 28. 第七轮审查修复（2026-08-10，I1-I3）

- **I1 全链容错**：写手A/B、润色A/B、审稿A/B 增加 onError 容错——A 轨任意
  LLM 节点失败不再拖死 B 轨（此前 A 轨写手/润色/审稿短路会级联断掉质量门A →
  提炼A → 整理A → 写手B 整条链）。配合质量门软失败、提炼/整理容错，任意失败
  都落到「passed:false 显式落库 + 健康轨继续」，无痕丢章场景消除；validator
  断言 6 节点容错。
- **I2 兜底依赖说明**：合并兜底依赖 n8n 深度优先分支执行（质量门先于兜底运行），
  代码层面已按此模型校验，README 已知限制标注「真机首次日更时验证双轨失败场景」。
- **I3 骨架路径补齐**：pipeline 审稿 chat 传 max_tokens=2000、记忆传 2400，
  autopilot 路径不再有截断风险。
- **验证**：后端 144 + 前端 6 全绿；15/15 表达式通过；validator 通过；
  三份工作流重新部署激活（64/8/4）；服务重启正常。

## 27. 第六轮审查修复（2026-08-10，H1-H7）

- **H1 Python 骨架截断**：pipeline 写手/润色显式传 max_tokens（按字数动态），
  planner 传 3000；MockLLMClient 同步支持 max_tokens 参数。
- **H2 提炼/审阅类 max_tokens**：memory 2400、reviewer/reader/eic/guard/
  work_meta 2000，结构化摘要与六类审稿不再被 1600 兜底截断。
- **H3/H7 双轨隔离与失败策略**：提炼剧情A/B、整理剧情A/B 加
  onError 容错——A 轨记忆步骤失败不再拖死 B 轨；失败策略统一为三层并写入
  README（写手/润色/审稿短路保不发布坏文、提炼/整理容错保双轨、守护/读者/
  主编降级放行由质量门兜底）。
- **H4 合并兜底语义**：改为读取质量门A/B 的 passed（整理剧情前已执行），
  不再恒输出 failed_both 占位；README 描述与实现一致。
- **H5 无活跃书显式失败**：算章节号匹配不到当前书直接 throw 告警，
  不再静默取番茄账号第一本书。
- **H6 质量门降级文档化**：README 4.3 与已知限制如实说明读者/主编缺失时的
  降级放行条件。
- **validator**：提炼/整理 onError、兜底读质量门、算章节号显式失败断言。
- **验证**：后端 144 + 前端 6 全绿；15/15 表达式通过；validator 通过；
  三份工作流重新部署激活（64/8/4）；服务重启正常。
# 流水线进化机制（2026-08-10）
# 知识库逻辑重构（2026-08-11）
设定知识库从「谁都能写、写坏再说」改为「写入端守规矩」：
- `tools/novel_knowledge.py` 新增实体名规范化（短名词、去整句/括号/书名号）、相似实体合并（`upsert_ex` + `find_similar`）、冲突内容自动落 `knowledge_drafts` 草案；`sync_from_bible` 的 `world_rules` 支持结构化 `{rule, content}`，金手指只入 item，文风/人物关系不再混入规则与剧情分类；`sync_from_chapters` 的角色状态改为更新同名主实体（版本化），不再产生「名字·状态」平行条目。
- 三个 Agent 提示词联动：planner 的圣经规则改为结构化输出并要求角色名全书唯一；memory 的角色状态键必须与角色卡一致（禁止漂移成新角色）；guard 审核项新增「角色名」类型，专门拦截形近/音近的疑似漂移。
- `tools/clean_novel_knowledge.py` 一次性清理脚本（默认 dry-run，`--apply` 前自动备份）：规范化超长实体、合并「·状态」条目、去重 item/power 金手指、合并高度相似规则。真实库已执行两轮：62 条 → 58 条，超长实体清零。
- web_api 新增版本历史与图谱接口（`/api/novel_knowledge/history`、`/api/novel_knowledge/graph`），手动录入返回 `merged_into`/`similar` 提示。

# 流水线进化机制（2026-08-10）
