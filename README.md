# novel-pipeline

AI 网文自动生成与发布流水线：n8n 定时编排 + DeepSeek 多 Agent 协作 + Python
记忆/知识层（SQLite）+ 番茄小说发布 + Electron 桌面控制台。

目标场景：**每天 08:00 自动生成两章并提交番茄审核**，月预算 100 元内，全程无人值守；
出现 Cookie 失效、预算超限、重复触发等情况会自动熔断并写告警。

## 一、整体架构

```text
[n8n 日更工作流·61 节点]           [n8n 周会工作流·7 节点]      [n8n 知识管家·每日 03:30]
 每日 08:00 / 手动补更               周日 08:10                  自动维护知识库
  ├─ 备份→预检→查章节→读记忆包        ├─ 采集热点(双轨)           ├─ 市场知识包自动更新
  ├─ 生成(Planner/守护/写手×2/        ├─ 读上下文→3 轮会议        ├─ 经验卡/废弃草案
  │  润色/审稿/终审/记忆官)           └─ 蒸馏经验卡→落库          └─ 知识包健康检查
  ├─ 同步设定知识库(版本化)
  └─ 发布(建草稿→保存→提交→复核)
                          │
                          ▼
        本地 Agent 代理 POST /api/agent/run
        （DeepSeek function calling：get_knowledge / get_novel_knowledge）
                          │
                          ▼
    SQLite（作品/章节/设定知识库/伏笔/角色/会议/成本/审计）
                          │
                          ▼
      Electron 桌面控制台（SSE 实时推送 + 命令面板 Ctrl+K）
```

LLM 不直接联网：爬取、检索、落库全部由 Python 代码执行，模型只负责在
`tools` 声明中看到工具、自主决定调用、基于返回内容推理。

## 二、Agent 矩阵（11 位）

| Agent | 文件 | 模型 | 职责 |
| --- | --- | --- | --- |
| 文策 | planner.md | pro | 故事圣经与两章细纲（情绪/定位/伏笔埋收） |
| 守界 | guard.md | flash | 动笔前拦截 OOC/吃书/时间线/伏笔矛盾 |
| 墨白 | writer.md | pro | 按细纲+角色卡+守护约束写 2000 字正文（A/B） |
| 润物 | editor.md | flash | 去 AI 味、翻译腔、标点、节奏收紧（A/B） |
| 守正 | reviewer.md | flash | 六类底线问题与风格检查（A/B） |
| 阿读 | reader.md | flash | 追读欲/钩子/情绪满足评分（A/B） |
| 掌印 | eic.md | flash | 仲裁双审冲突，输出 verdict 与 must_fix（A/B） |
| 录事 | memory.md | flash | 提炼摘要、角色状态、事件、伏笔台账（A/B） |
| 书案 | work_meta.md | flash | 书名/简介/标签/主角/卷目标 |
| 终局 | ending_judge.md | flash | 完结评估：剧情进度、伏笔回收、收尾建议 |
| 博闻 | knowledge_keeper.md | flash | 知识库策展人：定时维护、经验整合、热点蒸馏 |

每位 Agent 有人物档案（性格/口吻/价值观/情绪基线）+ 日常任务 + 日记/周记/
会议三种模式；提示词资产化在 `prompts/agents/*.md`，编辑后一键渲染部署。

## 三、知识体系（成长闭环）

### 1. 通用知识包 `prompts/knowledge/*.md`

六个包：开篇钩子、节奏爽点、人设与关系、巧思伏笔、去 AI 味/文本质感、
市场选题与读者心理。frontmatter 标注适用角色（agents）、类型（craft/market/
generic）、关键词。短硬规则（去 AI 味黑名单）常驻，长文内容按需工具调用。

### 2. 每部小说的设定知识库 `novel_knowledge`

卡帕西式单一事实源：角色状态、世界观规则、物品/金手指、势力、地点、力量体系、
剧情事实、时间线八个分类，每条版本化——更新不覆盖旧值，旧版进历史表。
日更时记忆官提炼剧情后自动同步；Agent 通过 `get_novel_knowledge` 工具按需查询，
禁止凭记忆编造或遗忘设定。作品库页可查看/编辑。

### 3. 经验卡 `knowledge_drafts`

周会/专题会议后自动蒸馏经验卡草稿，前端一键采纳（写入知识库并重新部署）或拒绝；
博闻定时任务产出的知识包更新/废弃建议同样走草稿 + 人工审批，防模型自我循环污染。

## 四、工具式知识调用

15 个日更 LLM 节点全部改为调用本地 `POST /api/agent/run`（`tools/agent_tool_loop.py`）：

- 首轮带 `tools` 声明（`get_knowledge` 通用知识包、`get_novel_knowledge` 本书设定库），
  不传 `tool_choice`（兼容 DeepSeek V4 thinking 模式，强制 tool_choice 会 400）
- 模型自主发出 `tool_calls` → 本地检索 → `role:"tool"` 回传 → 二轮输出最终结果；
  无调用则单轮返回；工具异常自动降级单轮并记录
- 会议发言（`tools/agent_meeting.py`）同样接入工具循环，直播气泡显示
  「⚙ get_novel_knowledge(破碗)」调用标签，调用全程可观测

## 五、会议中心

专题会议不锁死轮数：每轮结束由用户决定「继续下一轮」或「✓ 结束讨论并总结」，
20 轮硬上限兜底；主席点将、自然口语发言（speech 字段）、结构化记录折叠展示、
会议落库归档。周会为定时自动流程（固定三轮 + 自动蒸馏）。刷新页面可恢复进行中的会议。

会议报告支持 `cover_prompt`（封面 AI 绘画提示词，含画面主体/风格/色调/构图/文字排版要求）：
讨论到新书选题时由主席写入，展示在会议结论与作品库新书卡片上，可直接复制到豆包等文生图工具。
专题会议结束后决策统一落盘（蓝图/封面提示词/下一本选题）。

### 自动建书（一键）

新书创意确认（status=ready）后，作品库页「一键自动建书」按钮调 `tools/create_book.py`：
自动匹配番茄分类与标签、填写书名/简介（单行≥50字）/主角名（清洗后≤5字），调用
`/api/author/book/create/v0/` 创建书籍，再查卷列表自动绑定 `book_id`/`volume_id`
并写入 `~/.n8n/.env`，状态直接进入 publishing，日更自动切换到新书。手动绑定保留为备用。
注意：番茄每天最多创建 1 本新书，失败当天无法重试。

## 六、热点采集（HTML + 浏览器双轨）

- 每源先 HTML 直抓（纵横可用），失败或空源自动降级 bb-browser（复用真实浏览器
  登录态，每次重新 open，eval 提取书名/作者/简介/最新章节，字体反爬清洗）
- 周会工作流开头自动采集（每周与周会同频），首页「立即采集」按钮手动触发
- 数据落盘 `hot_topics.json`，注入日更上下文、周会材料、选题会与博闻蒸馏

## 七、数据层（SQLite）

- `novels` / `volumes` / `chapters` / `chapter_content`：作品与章节
- `novel_knowledge` + `novel_knowledge_history`：每书设定知识库（版本化）
- `characters` / `character_evolution` / `plot_threads`：角色与伏笔台账
- `chapter_summaries` / `quality_reports` / `publish_logs`：记忆、质量、发布审计
- `agent_diaries` / `agent_states`：Agent 日记（daily/weekly/meeting）与心情
- `weekly_meetings` / `meeting_sessions`：周会档案与专题会议状态机
- `knowledge_drafts`：经验卡与知识包更新草稿
- `cost_logs` / `audit_logs`：成本台账与全量留痕

## 八、安全与加固

- n8n 仅监听 `127.0.0.1`；凭据在 `~/.n8n/.env`，仓库不存密钥
- Cookie 失效 / 预算超限 / 重复触发自动熔断并写 `alerts.log`；每日自动备份数据库
- 发布失败短路不丢记录；A/B 分支相互隔离
- 知识包自动更新有缩水保护（新正文 < 原 50% 转人工草稿）；会议 20 轮上限

## 九、快速开始

```bash
pip install -e .

# 1. 配置 ~/.n8n/.env（见 .env.example）：DEEPSEEK_API_KEY / FANQIE_COOKIE 等
# 2. 启动监控 API（8000 端口）或直接启动 Electron 桌面
python -m novel_pipeline.web_api --db demo.db --port 8000
# 3. 导入/更新 n8n 工作流：n8n/novel_workflow.json、architect_weekly.json、
#    knowledge_keeper.json；渲染前先跑 tools/render_workflow.py
python tools/render_workflow.py
node tools/validate_workflow_deep.mjs
# 4. 测试
uv run pytest tests -q        # 后端 92 项
cd webapp && npm test -- --run # 前端 6 项
```

## 十、桌面控制台

Electron（frameless + 自绘标题栏 + 托盘 + 系统通知），启动自动拉起 API：

```bash
cd desktop
npm install
npm start        # 开发模式
npm run dist     # NSIS 安装包（desktop/release/）
```

11 个分区：仪表盘（状态/今日任务/最近会议/工作流控制/KPI/热点）、作品库
（大纲/主角/角色卡/设定知识库）、章节管理、Agent 管理（提示词编辑 + 日记/心情 +
知识库 + 经验卡）、成本中心、执行记录、阅读数据、系统设置、会议中心（直播/档案）、
留痕档案。快捷键：`Ctrl+K` 命令面板、`Ctrl+Shift+R` 强制刷新。

## 十一、已知限制

- 日更节点经本地代理调用，8001 API 需在线（失败走现有执行告警）
- 番茄字体反爬可能导致部分简介乱码；书名/作者/最新章节正常
- 会议进行中刷新可恢复现场，但关闭窗口后会议线程随 API 进程退出
- `meeting_sessions` / `knowledge_drafts` 数据持续积累，暂无自动清理
- DeepSeek V4 thinking 模式下模型偶尔不调用工具直接回答（属已知行为，单轮兜底）

## 文档

- [docs/evolution.md](docs/evolution.md)：进化机制与本次成长系统升级记录
- [n8n/README.md](n8n/README.md)：运维、番茄发书流程、成本单价
- [ARCHITECTURE.md](ARCHITECTURE.md)：架构决策
