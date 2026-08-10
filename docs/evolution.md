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

- **python 不在 PATH**：所有 ExecuteCommand 的 `python` 换成
  `C:/Users/.../Python311/python.exe` 绝对路径。
- **cwd 漂移**：n8n 进程工作目录是 `~/.n8n`，所有相对脚本路径改为绝对路径；
  大 payload（周会蓝图/日更结果）不再走命令行（超过 cmd.exe 8191 字符限制），
  改为 code 节点写 `n8n_tmp/*.json`，Python 端用 `--file` 读取。
- **Code 节点模块限制**：`~/.n8n/.env` 增加 `NODE_FUNCTION_ALLOW_BUILTIN=fs`。

开机自启：`shell:startup` 下放了三个 vbs（n8n、8000/8001 面板服务），
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
