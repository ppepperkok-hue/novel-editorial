# 流水线进化机制（2026-08-10）

流水线的可持续性靠三条：**提示词资产化**、**配置驱动生成**、**数据反馈回路**。
改写作风格、调整模型、加一个 Agent，都不需要再手改 66KB 的工作流 JSON。

## 1. Agent 提示词资产化

13 个 LLM 节点的 system prompt 抽到了 `prompts/agents/*.md`，每个文件带
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
