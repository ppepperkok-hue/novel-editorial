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
