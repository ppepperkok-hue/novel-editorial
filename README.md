# novel-pipeline · AI 网文自动生成与发布流水线

一套面向「番茄小说」副业的**全自动网文工作流**：n8n 定时编排 + DeepSeek 多 Agent 协作 +
Python 记忆/知识层（SQLite）+ 番茄 HTTP 发布 + Electron 桌面控制台。

目标场景：**每天 08:00 自动生成两章并提交番茄审核**；月预算 100 元内全流程无人值守；
出现 Cookie 失效、预算超限、重复触发等异常自动熔断并写告警。

项目仓库：<https://github.com/ppepperkok-hue/novel-pipeline>

## 目录

- [一、核心指标](#一核心指标)
- [二、架构总览](#二架构总览)
- [三、快速开始](#三快速开始)
- [四、自动日更流水线（64 节点）](#四自动日更流水线64-节点)
- [五、多 Agent 系统（11 位）](#五多-agent-系统11-位)
- [六、知识体系与成长闭环](#六知识体系与成长闭环)
- [七、热点采集（HTML + 浏览器双轨）](#七热点采集html--浏览器双轨)
- [八、会议系统（周会 / 专题会议）](#八会议系统周会--专题会议)
- [九、自动建书与封面提示词](#九自动建书与封面提示词)
- [十、数据层（SQLite）](#十数据层sqlite)
- [十一、监控、告警与经济模型](#十一监控告警与经济模型)
- [十二、前端与桌面控制台](#十二前端与桌面控制台)
- [十三、安全与加固](#十三安全与加固)
- [十四、目录结构](#十四目录结构)
- [十五、开发、测试与部署](#十五开发测试与部署)
- [十六、已知限制与风险](#十六已知限制与风险)
- [十七、后续路线](#十七后续路线)

## 一、核心指标

| 指标 | 数值 | 控制位置 |
| --- | --- | --- |
| 日更节奏 | 每天 2 章（约 2000-2200 字/章） | n8n 每日触发 + `settings.daily_chapters` |
| 月预算 | 100 元 | `settings.monthly_budget` + 预检熔断 |
| 成本单价 | pro 0.01 元 / flash 0.002 元每千 token | `~/.n8n/.env` 的 `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` |
| 平台 | 番茄小说（Cookie + CSRF 鉴权） | `~/.n8n/.env` 的 `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` |
| 发布方式 | 存稿池优先：有存货发存货，没存货现造 | `tools/check_stock.py` + `tools/publish_stock.py` |
| 健康线 | 存稿池 < 3 章触发断更预警 | `novel_pipeline/scheduler.py` 的 `SAFE_BACKLOG` |
| 测试基线 | 144 个后端 unittest + 6 个前端 Vitest | `python run_tests.py` / `cd webapp && npm test` |

## 二、架构总览

```text
[n8n 日更工作流 · 64 节点]              [n8n 周会工作流 · 7 节点]        [n8n 知识管家 · 4 节点]
  每日 08:00 / 手动 webhook                每周日 08:10 / 手动              每日 03:30 / 手动
  ├─ 备份 → 预检 → 查章节号 → 生成作品资料  ├─ 采集热点(双轨)                ├─ 读热点/知识包/草稿/质量反馈
  ├─ 读本地资料(记忆包) → Planner → 守护    ├─ 读上下文(周会材料+简报)       ├─ 博闻维护知识库
  ├─ 写手A/B → 润色 → 审稿 → 读者审稿       ├─ 开会(周记→点将→3轮→总结)     └─ 市场类自动更新 / 技巧类走人工草稿
  │   → 主编终审 → 质量门 → 排版 → 提炼剧情 ├─ 蒸馏经验 → 落盘决策
  ├─ 查存稿 → 发布存稿(三步) / 新建草稿     └─ 封面提示词落盘
  ├─ 提交发布 → 校验 → 复核
  ├─ 汇总 → 记录作品资料 → 采集阅读数据 → 全员写日记 → 同步设定知识库 → 结束
  └─ 存稿分支：发布存稿 → 采集阅读数据 → 全员写日记 → 同步设定知识库 → 结束
                       │
                       ▼
        Python 本地代理 POST /api/agent/run（DeepSeek function calling：
        get_knowledge 通用知识包 / get_novel_knowledge 本书设定库）
                       │
                       ▼
        SQLite：作品/章节/设定知识库/伏笔/角色进化/会议/日记/心情/成本/审计
                       │
                       ▼
        web_api（127.0.0.1:8000）→ Electron 桌面控制台（React + Vite + SSE 实时推送）
```

分层职责：

- **编排层（n8n）**：只负责时序与分支，所有业务逻辑在本地 Python 脚本执行，工作流 JSON 由
  `tools/render_workflow.py` 从 Agent 提示词资产生成，避免在画布里维护大段提示词。
- **智能层（prompts/agents + tools/agent_tool_loop.py）**：11 位人格化 Agent，通过原生
  function calling 按需调用知识工具；LLM 不直接联网，爬取、检索、落库全部由 Python 代码执行。
- **记忆层（SQLite）**：故事圣经、章节摘要、角色状态、伏笔台账、设定知识库（版本化）、
  Agent 日记/周记/心情、会议档案、成本与审计全量落库。
- **发布层（tools/publish_stock.py + tools/create_book.py）**：直接调番茄作者后台 HTTP API，
  鉴权用 Cookie + CSRF，与真实浏览器登录态一致。
- **展示层（webapp + desktop）**：React 单页 + Electron 桌面壳，SSE 实时推送，托盘常驻。

## 三、快速开始

环境要求：Python 3.9+（仅标准库即可运行流水线与测试）、Node.js 18+、n8n（自托管）、
番茄小号（已完成实名认证）。桌面 `desktop.py` 后备入口需要 `pip install -e ".[desktop]"`
（pywebview）。

```bash
# 1. 安装
cd novel-pipeline
python -m pip install -e .          # 或使用 uv
cd webapp && npm install && npm run build
cd ../desktop && npm install

# 2. 配置凭据 ~/.n8n/.env（见 .env.example）
#    DEEPSEEK_API_KEY / FANQIE_COOKIE / FANQIE_CSRF_TOKEN
#    COST_PRO_PER_1K / COST_FLASH_PER_1K / MONTHLY_BUDGET / N8N_API_KEY
#    PYTHON_EXE / PIPELINE_ROOT（n8n executeCommand 运行环境，换机器只改这里）
#    PANEL_TOKEN（可选，写接口的 Bearer 加固）

# 3. 启动控制台 API（8000 端口，Electron 会自动拉起）
python -m novel_pipeline.web_api --db demo.db --port 8000

# 4. 桌面控制台
launch_desktop.vbs                     # 开发态 Electron
cd desktop && npm run dist             # 或构建 NSIS 安装包

# 5. 部署工作流（先渲染，再导入 n8n）
python tools/render_workflow.py
node tools/validate_workflow_deep.mjs
# 导入 n8n/novel_workflow.json、architect_weekly.json、knowledge_keeper.json 并激活；
# 也可以在「Agent 管理」页保存任一 Agent 后点「部署」完成日更工作流推送。

# 6. 演示数据（可选）
python -m novel_pipeline.seed_demo --chapters 5 --published 2 --reviewed 2
```

完整测试（仅标准库，无需安装依赖）：

```bash
python run_tests.py
cd webapp && npm test && npm run build
```

## 四、自动日更流水线（64 节点）

日更工作流 `n8n/novel_workflow.json`（n8n 工作流 ID `SkLUnm3uRyBSY84F`）是整条流水线的核心。
节点按阶段划分如下。

### 4.1 触发与预检

- **每日触发 / 手动触发**：`scheduleTrigger` 默认 08:00，可从前端「系统设置」改时间并自动部署；
  `webhook` 手动触发对应前端「立即更新」按钮。
- **备份数据库**：`tools/backup.py` 在每次日更前复制 `demo.db` 到 `backups/`，只保留最近 3 份。
- **预检**：`tools/preflight.py` 在生成前做四项检查，任一失败即短路（写 `alerts.log` 并审计）：
  1. **Cookie 校验**：调番茄 `book_list/v0` 验证登录态，避免白白消耗 LLM 预算；
  2. **当日幂等**：今日已有 `published` 章节则跳过，防重复发布；
  3. **预算熔断**：本月 `cost_logs` 累计 ≥ 预算则跳过；
  4. **并发锁**：`n8n_tmp/daily.lock`（O_EXCL 原子创建）防止定时与手动同时触发双发；
     Windows 下用 OpenProcess 检测进程存活（不会误杀进程），锁龄超过 2 小时才按
     陈旧回收（正常一次日更 15+ 次 LLM 调用可能超过 30 分钟）；运行结束由
     「结束」节点释放。

### 4.2 作品资料与记忆包

- **查章节号**：调番茄 `book_list/v0` 拿 `chapter_number`，按「当前最大章号 +1」算
  A 章 = N、B 章 = N+1；`chapter_number` 的真实语义（是否本身已是下一章号）需真实
  登录态核对，见「已知限制」。
- **生成作品资料**：`work_meta` Agent 生成书名/简介/标签/主角名/卷目标；只有书还是默认名或
  简介过短时才调 `modify_book/v0` 提交番茄，避免每轮覆盖已有资料。
- **读本地资料**：`tools/get_meta.py` 组装「写前记忆包」，这是连贯性的关键——每章生成前注入：
  故事圣经（世界观/角色卡/金手指/主线）、10 章蓝图、最近 3 章摘要、上一章结尾原文、
  角色当前状态、活跃伏笔台账、已有章节标题（防重名）、热点选题、读者反馈（完读率/追读率）、
  每书设定知识库快照、目标字数与风格微调。
- **设定题材**：从 `settings` 读取题材与风格，供 Planner 使用。

### 4.3 生成链路（A/B 双轨）

每章经过 7 个智能节点 + 1 个确定性质量门：

1. **Planner出大纲**（pro）：生成/增量更新故事圣经 + 两章细纲，每章标注定位、情绪、钩子类型与伏笔埋收；
2. **守护细纲**（flash）：动笔前拦截 OOC、吃书、伏笔矛盾、时间线冲突，输出约束与角色言行要点；
3. **写手A/B**（pro）：按细纲 + 角色卡 + 守护约束写约 2000-2200 字正文；B 章串行承接 A 章结尾；
4. **润色A/B**（flash）：执行中文去 AI 味硬规则（翻译腔、空泛大词、破折号、排比、口号化收束）；
5. **审稿A/B**（flash）：六类底线问题——时间线矛盾 / 设定崩坏 / 人物 OOC / 重复情节 / 信息泄露 / 伏笔死结；
6. **读者审稿A/B**（flash）：追读欲、章末钩子、情绪满足评分；
7. **主编终审A/B**（flash）：仲裁审稿与读者审稿冲突，输出 `verdict` 与 `must_fix`；
8. **初始化设定知识库**（Planner 出 bible 后立即执行）：把首轮故事圣经同步进
   `novel_knowledge`（世界规则/角色/关系/金手指/主线/文风），幂等不重复版本化——
   第一章发布前 Agent 就能查到完整世界观；收尾「同步设定知识库」还会兜底补跑。
9. **质量门A/B**（确定性代码）：终审 `passed=true` 且正文字数 ≥1500 才放行；
   机械质量（AI 高频词/感叹号/省略号/字数）与终审任一不过都返回 `passed:false`
   （不再抛错中断 B 轨），失败原因随汇总落库；质量门结果写入 `quality_reports`，
   仪表盘质量指标在 n8n 主链路同样有效。

A/B 双轨互相隔离：质量门失败在排版处短路（不建草稿、不发布），另一章照常生成发布；
**失败显式留痕**——质量门失败章节落库为 `draft` + 错误原因（publish_logs 可见），
发布失败章节保留 `reviewed` 进存稿池，次日由「发布存稿」自动补发。

失败策略分三层（防中断与防坏文之间的取舍）：写手/润色/审稿失败直接短路该轨（不发布
坏文）；提炼/整理节点容错降级（A 轨记忆步骤失败不会拖死 B 轨）；守护/读者/主编缺失时
降级放行并带 note 标记——此时「机械检查 + 逻辑审稿通过」仍会发布，质量兜底弱于
全绿校验（比 README 原述的「终审必过」宽松，属有意取舍）。

### 4.4 排版、提炼与发布

- **排版A/B**：正文按换行切 `<p>`；模型输出整段无换行时，按句号/问号/叹号每 80-140 字自动断段兜底。
- **提炼剧情A/B + 整理剧情A/B**（memory Agent）：逐章提取结构化摘要、角色状态变化、世界事件、
  伏笔埋设/回收，写回 `chapter_summaries` / `characters` / `world_events` / `plot_threads` /
  `character_evolution`，供次日记忆包与设定知识库使用。
- **查存稿 / 存稿充足？ / 发布存稿**：`tools/check_stock.py` 读存稿池（`reviewed` 章节）与本次目标；
  有存货直接 `tools/publish_stock.py` 发布，没存货走「新建草稿 → 保存内容 → 提交发布」实时链路。
  存货策略让测试期多余章节自动留存，断更时也不至于空窗。
- **发布三步**（接口经 OpenNovel 等开源实现交叉验证，真实上线前需账号实测）：
  `new_article/v0` 拿 `item_id`+`volume_id` →
  `cover_article/v0` 保存标题正文 → `publish_article/v0` 提交审核（`use_ai=2` 声明 AI 创作）。
- **校验发布 / 复核发布**：n8n 链路发布后查 `chapter_list/v1` 确认状态，失败即短路；
  Python 工具链（`publish_stock.py` / `FanqieHttpAdapter`）发布后做 best-effort 复核，
  未在列表中找到会返回警告而不阻塞。
- **合并兜底**：`整理剧情A → 合并兜底 → 合并发布结果`——当 A/B 双轨同时失败时
  （无任何校验输出），兜底节点补一个占位结果，保证「汇总运行结果」仍会执行，
  质量门失败章节照常落库留痕；直发成功时兜底返回空数组，不干扰原链路。

### 4.5 收尾沉淀

- **汇总运行结果 → 记录作品资料**：`tools/record_work.py` 把整轮结果落库：作品信息 upsert
  （**不覆盖既有状态机**，finished 书不会被复活）、角色 upsert（保留配角状态）、分卷、
  章节（正文进 `chapter_content`）、发布日志、成本（按模型单价折算，`run_id` 幂等去重）。
- **采集阅读数据**：`tools/collect_reader_stats.py` 调番茄章节数据接口，写
  `demo_data/reader_stats.csv`（章节、完读率、追读率）。
- **全员写日记**：`tools/write_diaries.py --mode daily` 让 11 位 Agent 各写一条当日日记
  （做了什么/观察/感受/顾虑/想法），落 `agent_diaries`，保留 8 周自动清理。
- **同步设定知识库**：`tools/novel_knowledge.py --sync-latest` 把最近章节的角色状态/事件/时间线
  同步进每书设定知识库（版本化，历史可查）。

两条触发路径（现造 / 存稿充足）都汇入完整收尾链：采集阅读数据 → 全员写日记 →
同步设定知识库 → 结束；「发布存稿」位于两条路径的汇合处，存稿分支先发存货再收尾。

## 五、多 Agent 系统（11 位）

所有 Agent 的人格资产在 `prompts/agents/*.md`，文件头 frontmatter 记录 `model`、
`temperature` 与可选 `max_tokens`，正文是人物档案 + 三种模式指令（日常任务 / 日记周记 /
会议发言）。

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

### 5.1 人格化

每位 Agent 有人物档案：姓名、身份、性格、说话风格、价值观、核心关注点、情绪基线；
日记模式/周记模式/会议模式让 Agent 在不同场景下以第一人称自述。目标是把输出从「AI 腔」
拉回「有立场、有情绪、会反思」的协作角色，而不是单纯的提示词模板。

### 5.2 代理模式（Prompt 资产 ↔ 工作流）

- `tools/export_agent_prompts.py`：旧版（非代理模式）工作流的系统提示词导出入口；
  代理模式下提示词资产直接维护在 `prompts/agents/*.md`，脚本会明确提示无需导出；
- `tools/render_workflow.py`（`PROXY_MODE=True`）：反向把 Agent 资产渲染回工作流——
  日更 15 个 LLM 节点全部改为请求本地 `POST /api/agent/run`，n8n 只携带
  `agent / model / temperature / max_tokens / target_words / task`，系统提示词由
  `tools/agent_tool_loop.py` 在运行时组装；
- `node tools/validate_workflow_deep.mjs`：深度校验渲染结果；
- 前端「Agent 管理」页：编辑提示词/模型/温度 → 保存（自动 render + validate）→ 一键部署到 n8n。

这个闭环是「流水线进化」的入口：改一段人格提示词，保存即渲染 + 校验，再点「部署」
推送到 n8n，不需要手动改画布。

### 5.3 工具式知识调用（function calling）

Agent 首轮携带 `get_knowledge`（通用写作知识包）与 `get_novel_knowledge`（本书设定库）两个
工具声明（不传 `tool_choice`，兼容 DeepSeek V4 thinking 模式）。模型自主决定是否调用：

- 发出 `tool_calls` → 本地检索知识包/设定库 → 以 `role:"tool"` 回传 → 第二轮输出最终结果；
- 无调用则单轮返回；第二轮异常自动降级为返回首轮文本并记录；第二轮若模型仍发出多余
  `tool_calls` 会被显式标注 ignored（两轮策略），不阻塞流水线。

知识包不常驻上下文，避免长文提示词膨胀；短硬规则（去 AI 味黑名单）以 `generic` 类型常驻。

## 六、知识体系与成长闭环

### 6.1 通用知识包 `prompts/knowledge/*.md`

六个写作知识包：开篇钩子、节奏爽点、人设与关系、巧思伏笔、去 AI 味/文本质感、市场选题与
读者心理。每个文件带 frontmatter：`agents`（适用角色，可 `all`）、`type`
（craft 技巧 / market 市场 / generic 硬规则）、`keywords`、`source`、`updated_at`。
检索时按 agent 过滤 + 关键词匹配，命中后整包注入。

### 6.2 每书设定知识库 `novel_knowledge`

卡帕西式「单一事实源」：每本书的设定按 8 个分类存储——角色、世界规则、物品、势力、地点、
力量体系、剧情事实、时间线。每条记录版本化：更新不覆盖旧值，旧值进 `novel_knowledge_history`，
可追溯「第 N 章改了什么」。Agent 写作时不确定设定必须调 `get_novel_knowledge` 确认，
禁止凭记忆编造或遗忘设定（防吞设定）。**初始化由 Planner 的首轮故事圣经自动完成**
（`sync_from_bible`：世界规则/角色卡/人物关系/金手指/主线/文风），内容未变化时不会
重复版本化；之后每次日更由章节摘要增量同步角色状态、剧情事件与时间线。

### 6.3 世界观与人物卡数据链路

世界观/人物卡是三套分工明确的数据，避免单一事实源互相覆盖：

| 数据载体 | 角色 | 写入者 | 读取者 |
| --- | --- | --- | --- |
| `novels.outline.bible` | 定义层：角色卡/世界观/关系/金手指/主线/文风 | Planner 首轮创建、每轮增量；周会 `character_updates` 固化 | 写手/守护/审稿/读者/主编/记忆的 task 直接引用；get_meta 组装记忆包；周会材料 |
| `novel_knowledge` | 可查设定库：8 分类、版本化 | `sync_from_bible`（bible 初始化，每轮解析大纲后执行 + 收尾兜底）、`sync_from_chapters`（章节增量）、前端手动 | Agent 通过 `get_novel_knowledge` 按需查询（硬规则，禁止凭记忆） |
| `characters` + `character_evolution` | 动态状态层：当前状态与成长轨迹 | record_work（主角 + 章节摘要角色变化） | get_meta 合并进 bible 角色卡的 `current_state` 与写前记忆包 |

读取时机：

- Planner 出 bible → 「初始化设定知识库」立即同步（每轮都跑，幂等）→ 守护/写手/审稿
  等任何 Agent 查询设定库时拿到的都是最新世界观；
- 章节状态（角色当前状态/事件/时间线）在收尾 `sync-latest` 增量入库，供次日记忆包与
  周会使用；章节状态以「名字·状态」实体存储，不会覆盖 bible 初始化的角色卡；
- 首轮日更的 writing_context 不含 bible（读取早于 Planner），因此写手/守护/审稿/读者/
  主编/记忆的 task 都直接引用解析大纲的 bible，读者审稿与主编仲裁不缺设定上下文。

多书隔离：

- 所有按书数据（bible / novel_knowledge / characters / character_evolution /
  diaries / meetings / cost）均以 `novel_id` 隔离，前端作品库按书展示；
- Agent 每次调用携带当前书 `novel_id`（get_meta 输出 → 解析本地资料 → 渲染器注入
  全部代理节点），`get_novel_knowledge` 只查本书设定库，不会串书；
- 「全员写日记」绑定当前书（--novel-id），周会「读上下文 / 开会」绑定
  `FANQIE_BOOK_ID`（--book-id），多书并存时日记与会议材料不会写错书；
- 全局数据（settings / hot_topics / 知识包 / 成本单价）按设计跨书共享。

### 6.4 知识管家「博闻」（第 11 位 Agent）

`tools/knowledge_keeper.py` + n8n 定时工作流（每天 03:30 + 手动 webhook）：

- 输入：热点 `hot_topics.json`、当前知识包清单与正文尾部、待处理草稿、质量通过率、
  最近 7 天发布失败数；
- 输出：`auto_updates`（仅 market 类型自动更新并审计）、`draft_suggestions`（技巧/规则类落
  `knowledge_drafts` 人工采纳）、`deprecations`（废弃建议）；
- 缩水保护：模型把知识包改短到原正文 50% 以下时强制转人工草稿，防模型自我循环污染。

### 6.5 反思蒸馏 `tools/distill_lessons.py`

周会/专题会议结束后自动蒸馏 2-6 条可执行经验卡（受益 Agent、标题、教训与下次具体改法、依据），
落 `knowledge_drafts`。前端 Agent 管理页可预览/编辑草稿，采纳即写入知识包并自动
render + deploy 到 n8n，拒绝则归档。这样 Agent 的成长来自「会上讨论 + 数据反馈 + 人工把关」，
而不是直接让模型改自己的提示词。

## 七、热点采集（HTML + 浏览器双轨）

`novel_pipeline/hot_topics.py` 采集纵横/番茄/起点三个榜单：

- **HTML 直抓**（纵横实测可用）：正则提取 `book-name` 类链接与 `title` 属性；
- **浏览器降级**（番茄/起点实测需要）：HTML 失败或 0 条时调 bb-browser，每次任务重新
  `open` 页面（daemon 重启会导致 tab 失效，禁止缓存 tab id），`wait` 后 `eval` 提取
  书名/作者/简介/最新章节，字体反爬字符按可见字符清洗；
- 单源失败只记录错误不阻塞整体，结果落盘 `hot_topics.json`（每源标记 `method`：
  html / browser / error）。

数据流向：周会工作流开头自动采集（与周会同频）→ `get_meta.py` 注入日更上下文（近期热点
1000 字符）→ `architect_weekly.py` 注入周会材料 → 选题会与博闻蒸馏消费。首页有
「立即采集」按钮与各源状态、更新时间。

## 八、会议系统（周会 / 专题会议）

### 8.1 周会（每周日 08:10，n8n 7 节点）

1. **采集热点**：`hot_topics.refresh` 双轨抓取；
2. **读上下文**：`tools/architect_weekly.py` 输出 20 字段周会材料（作品状态、故事圣经、
   最近 8 章摘要、活跃伏笔、已有蓝图、阅读数据、热点、质量汇总、成本 token、设定库快照）
   与每位 Agent 的本周简报（`agent_briefs`：本周章数/字数/均分/通过率等）；
3. **开会**：`tools/agent_meeting.py` 完整流程：
   - **写周记**：每位 Agent 先回顾本周日记 + 工作简报 + 上周周记，自述本周干了什么/关键事件/
     学到什么/看法变化，并输出心情 `{satisfaction, concern, excitement, fatigue}`，
     落 `agent_diaries(weekly)` + `agent_states`；
   - **主席点将**：eic 读材料 + 全员心情，动态选出 ≤8 位参会者与议题；
   - **三轮通气**：每位 Agent 上下文 = 材料 + 本人简报 + 本人周记 + 心情 + 历史发言，
     发言固定六段结构：本周小结 → 我的感受 → 意见 → 顾虑 → 提案 → 优先级；
   - **主席总结**：eic 输出报告（决策/分歧/行动项/封面提示词）；
4. **蒸馏经验**：`distill_lessons` 落经验卡草稿；
5. **落盘**：`tools/apply_architect.py` 合并蓝图、更新读者画像/卷目标、存封面提示词、
   处理完结与下一本书创建。

### 8.2 专题会议（可交互，不锁死轮数）

`novel_pipeline/services/meeting_session.py`：首页「发起专题会议」输入主题即开会，
适合「讨论下一本书写什么」「这个剧情怎么发展」等即兴议题：

- 每轮结束停在 `awaiting_input`，用户可插入指示（如「聚焦男频玄幻」）再继续下一轮，
  或点「结束讨论并总结」；到达 20 轮自动封顶结束（不再等待用户操作）；
- 直播式展示：像群聊一样按轮次显示每位 Agent 的自然发言与知识工具调用标签；
- 结束后归档 `weekly_meetings(kind='topic')` + 每位参会者写 meeting 记忆 + 决策统一落盘；
- 刷新页面可恢复进行中的会议。

### 8.3 记忆与心情

- `agent_diaries`：daily（每天日更后）+ weekly（周会前）+ meeting（会后），保留 8 周；
- `agent_states`：每周心情（satisfaction/concern/excitement/fatigue），周会发言带着心情说，
  让 Agent 更像「有状态的人」而不是每次从零开始的函数；
- 前端「Agent 管理」页内嵌日记与心情编辑，可直接修改 Agent 的自述内容。

## 九、自动建书与封面提示词

### 9.1 一键自动建书 `tools/create_book.py`

新书创意确认（`status='ready'`）后，作品库页「一键自动建书」：

1. 调番茄 `category_list/v0` 与 `group_category_list/v0` 拉官方分类/标签列表，
   按题材 + 已有标签字符匹配（fallback 取前两条）；
2. 简介单行化并补齐 50 字，主角名清洗（去全角括号/别名/斜杠）截 5 字；
3. `POST /api/author/book/create/v0/` 建书（`original_type=1` 原创、`gender` 按题材判断）；
4. 查 `volume_list/v1` 拿默认卷 id，复用 `ending.bind_book` 落库并写
   `~/.n8n/.env` 的 `FANQIE_BOOK_ID` / `FANQIE_VOLUME_ID`；
5. 状态 ready → publishing，日更自动切换到新书；全程审计留痕。

注意：番茄每天最多创建 1 本新书，失败当天无法重试。手动绑定仍保留为备用入口。

### 9.2 封面提示词

会议主席总结报告新增 `cover_prompt` 字段（画面主体/风格流派/色调氛围/构图/文字排版要求），
落盘到 `novels.cover_prompt`（新书创建时随书携带）。作品库新书卡片与会议结论均可一键复制，
用户拿去豆包等文生图工具出封面后，自己在番茄后台上传（封面不阻塞发章节）。

## 十、数据层（SQLite）

`novel_pipeline/db.py` 定义全部表结构并自动迁移（`_migrate` 为旧库补列）：

| 表 | 内容 | 消费方 |
| --- | --- | --- |
| novels / volumes | 作品信息、状态机（planning→ready→publishing→finishing→finished；record_work 落库不覆盖既有状态）、封面提示词 | 前端作品库、日更 |
| chapters / chapter_content | 章节元数据 + 正文存档 | 章节管理、阅读器、发布 |
| characters / character_evolution | 角色卡 + 成长轨迹快照 | 记忆包、作品库 |
| world_events / plot_threads | 世界事件与伏笔台账（埋/收） | 守护、记忆包、周会 |
| chapter_summaries / quality_reports | 摘要与质量报告（含重写轮次） | 记忆包、成本中心 |
| publish_logs | 发布审计（成功/失败/AI 声明） | 仪表盘、监控 |
| novel_knowledge / novel_knowledge_history | 每书设定知识库（版本化） | agent 工具、前端 |
| cost_logs / settings | 成本台账与系统设置 | 预算熔断、成本中心 |
| agent_diaries / agent_states | Agent 日记/周记/会议记忆 + 心情 | Agent 管理、周会 |
| weekly_meetings / meeting_sessions | 周会档案与专题会议状态机 | 会议中心 |
| knowledge_drafts | 经验卡/知识包更新草稿 | Agent 管理 |
| audit_logs | 全量留痕（预检/设置/操作/发布/会议/知识） | 留痕档案页 |

## 十一、监控、告警与经济模型

- **健康检查** `novel_pipeline/monitor.py`：Cookie/CSRF 缺失、断更预警（存稿 <3）、
  发布失败条数、成本超限，结果实时进仪表盘；`alerts.log` 记录告警原文。
- **副业测算** `novel_pipeline/economics.py`：把番茄全勤门槛（签约 + 累计有效过审 10 万字 +
  当月听读分成 ≥500 元 + 日更过审）显式建模，输入章节成本/日更量/预期分成，输出月净利与
  盈亏平衡听读分成，帮助判断「副业不亏」的边界。
- **阅读反馈** `novel_pipeline/data_feedback.py`：完读率 <20% 或追读率 <30% 的章节标记为
  低质章节，提示反查大纲节奏与章节钩子；`tools/ai_taste_check.py` 提供 AI 味检测
  （华丽辞藻密度/填充短语/连续感叹号/四字排比堆砌评分），前端章节页可手动触发。

## 十二、前端与桌面控制台

### 12.1 React 前端（webapp）

十个页面：仪表盘 / 作品库 / 章节管理 / Agent 管理 / 成本中心 / 执行记录 / 阅读数据 /
系统设置 / 会议中心 / 留痕档案。关键交互：

- 仪表盘：KPI 总览（作品/章节/质量/成本/健康）、工作流在线状态、最近会议摘要、热点选题区块
  （立即采集）、「立即更新」「开会」入口；
- 作品库：每部作品的大纲/主角/角色卡/世界规则/设定库编辑、封面提示词复制、新书确认与
  一键自动建书；
- Agent 管理：提示词/模型/温度编辑 → 保存渲染校验 → 部署；日记与心情编辑；经验卡与知识库
  草稿采纳/拒绝；
- 会议中心：发起专题会议、直播发言流、结束总结、历次档案；
- 系统设置：日更开关/预算/目标字数/更新时间（改时间自动部署 n8n）/风格微调/开机自启/主题。
- 实时性：SSE `/api/events` 5 秒快照 + 5 秒轮询兜底；Ctrl+K 命令面板；数字键切页；
  Ctrl+R 刷新；深浅主题。

### 12.2 Electron 桌面壳（desktop）

- 无边框窗口 + 自绘标题栏，托盘常驻（打开控制台/立即更新一章/立即跑周会/退出）；
- 启动时自动拉起 8000 端口 web_api（已占用则复用），窗口关闭最小化到托盘；
- 执行完成系统通知（轮询 `/api/executions` 状态变化）；
- 单实例锁、开机自启开关、electron-builder NSIS 安装包 + electron-updater 自动更新；
- `launch_desktop.vbs` 提供开发态一键启动。

## 十三、安全与加固

- 凭据只在 `~/.n8n/.env`（Cookie / CSRF / DeepSeek key / n8n API key），仓库不存密钥；
  n8n 仅监听 `127.0.0.1`；
- web_api 强制绑定 `127.0.0.1`（拒绝 `--host` 暴露到局域网）；所有请求校验 Origin 必须为
  本机（跨站 CSRF 直接 403），POST 拒绝 `text/plain`（堵死 no-cors 简单请求）；可选
  `PANEL_TOKEN`：配置后「POST 且无 Origin」的写请求必须带 Bearer 头（浏览器与 GET 不受
  影响，面板可正常打开；n8n 节点由渲染器自动注入）。注意这是本机信任模型下的纵深防御，
  无法防住能伪造本机 Origin 头的本地进程；
- POST 请求体上限 5MB；500 响应不向客户端泄露内部异常（写入 `alerts.log`）；
- 知识包读写与 Agent 提示词保存都做路径穿越防护（resolve 后必须仍在对应目录内且为
  `.md`），静态服务同样防目录逃逸；
- 预检熔断：Cookie 失效、预算超限、当日重复、并发锁四重防护，任一命中即短路并告警；
- 发布失败短路不丢记录：质量门失败标 draft + 错误、发布失败保留 reviewed，A/B 分支隔离，
  次日可补发；autopilot 路径同样写 publish_logs；
- 知识包缩水保护（新正文 < 原 50% 转人工草稿）；会议 20 轮上限；热点单源失败不阻塞；
- 番茄发布强制 `use_ai=2` 声明 AI 创作，发布日志记录 `ai_declared`，合规透明。

## 十四、目录结构

```text
novel-pipeline/
├── novel_pipeline/          # Python 库
│   ├── config.py            # 集中配置：路径 / env 加载 / 工作流 ID
│   ├── db.py                # SQLite schema + 自动迁移 + 数据操作
│   ├── llm_client.py        # DeepSeek 直连（chat_deepseek）+ 旧兼容 LLMClient/Mock
│   ├── web_api.py           # HTTP 路由壳（REST + SSE + 静态托管）
│   ├── services/            # 服务层：dashboard/control/n8n/agents/audit/misc/
│   │                        #   meeting_session/ending/knowledge
│   ├── planner.py / pipeline.py / quality_gate.py / novel_flow.py
│   ├── publisher.py / scheduler.py / autopilot.py      # 发布适配器 / 调度 / 计划任务
│   ├── monitor.py / economics.py / data_feedback.py    # 监控/测算/反馈
│   ├── backup.py / compliance.py / hot_topics.py       # 备份/合规/热点
│   └── desktop.py            # pywebview 后备桌面入口
├── prompts/
│   ├── agents/*.md           # 11 位 Agent 人格资产（frontmatter: model/temperature）
│   └── knowledge/*.md        # 6 个通用知识包（frontmatter: agents/type/keywords）
├── tools/                    # 流水线脚本
│   ├── render_workflow.py / export_agent_prompts.py   # Agent 资产 ↔ 工作流
│   ├── agent_tool_loop.py    # function calling 工具循环
│   ├── preflight.py / check_stock.py / publish_stock.py / create_book.py
│   ├── get_meta.py / record_work.py / write_diaries.py
│   ├── agent_meeting.py / architect_weekly.py / apply_architect.py
│   ├── knowledge_keeper.py / distill_lessons.py / novel_knowledge.py
│   ├── collect_reader_stats.py / ai_taste_check.py / app_settings.py
│   └── debug/                # 一次性调试/探索脚本（probe_*/cdp_*/query_*）
├── webapp/                   # React + Vite 前端（Electron 壳加载 dist）
├── desktop/                  # Electron 壳（main/preload/release.js）
├── web/                      # 旧版单文件 HTML 兜底页（web_api 在 dist 缺失时回退）
├── n8n/                      # 三个工作流 JSON（日更 64 节点 / 周会 7 节点 / 知识管家 4 节点）
├── docs/                     # evolution / planning / research
├── ai_words.json             # 共享 AI 味词表（Python 质量门与 n8n 质量门同源）
├── tests/                    # 144 个后端 unittest + 前端 Vitest
├── scripts/install_daily_task.ps1   # Windows 计划任务备选注册脚本
├── launch_desktop.vbs        # 开发态桌面一键启动
└── demo.db / exports / n8n_tmp / backups / hot_topics.json / alerts.log
```

## 十五、开发、测试与部署

### 15.1 修改 Agent

```bash
# 导出当前工作流提示词 → prompts/agents/*.md（首次或回归时）
python tools/export_agent_prompts.py   # 代理模式下会提示直接维护 prompts/agents/*.md

# 编辑 md 文件后渲染回工作流并深度校验
python tools/render_workflow.py
node tools/validate_workflow_deep.mjs
```

前端 Agent 管理页封装了上述流程：保存 = render + validate + 可一键部署。

### 15.2 测试

```bash
python run_tests.py          # 144 个后端测试（标准库 unittest）
cd webapp && npm test        # 6 个前端 Vitest 测试
cd webapp && npm run build   # 构建 dist 供 web_api 托管
```

覆盖范围：数据库迁移、Planner JSON 校验、质量门、端到端生成（Mock LLM）、调度/存稿池、
预检熔断、监控、成本测算、备份、热点（html/browser/error 三态）、知识包检索与草稿采纳、
知识管家、经验蒸馏、会议 dry-run 全链、工具循环三态、自动建书全链路、web_api 端点、
审计留痕、工作流渲染（保留 TARGET_WORDS 语义）、发布状态机（质量门失败落库/发布失败
补发）、鉴权与路径穿越、迁移去重（保留已发布章节）、成本超限告警等。

### 15.3 部署

- 开发态：`launch_desktop.vbs` 或 `python -m novel_pipeline.web_api --db demo.db --port 8000`；
- 安装版：`cd desktop && npm run dist` 产出 NSIS 安装包；打 tag 后 `--publish always`
  上传 GitHub Releases，客户端自动更新；
- 工作流推送：改完工作流 JSON 后校验并 PUT 到 n8n（前端「Agent 管理 → 部署」只推日更，
  周会/知识管家需手动导入或调用 n8n API）；
- 备选：`scripts/install_daily_task.ps1` 注册 Windows 计划任务运行 `autopilot`
  （不依赖 n8n 的模式，使用 `FanqieHttpAdapter` 真实三步发布，需同样配置
  `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` 与目标字数）。

### 15.4 升级与故障排查

升级流程（保持仓库与线上一致）：

```bash
git pull
python run_tests.py                # 后端回归
python tools/render_workflow.py    # 提示词资产 → 工作流
node tools/validate_workflow_deep.mjs
cd webapp && npm test && npm run build
# 推送三份工作流到 n8n（日更/周会/知识管家），重启 8000/8001 web_api
```

排查入口：

- **执行记录**：前端「执行记录」页 / n8n Executions，看失败节点与错误；
- **告警日志**：`alerts.log`（预检熔断、发布失败、成本超限、API 异常都会写）；
- **留痕档案**：前端「留痕档案」页（audit_logs：设置/操作/发布/会议/知识全量事件）；
- **数据**：`demo.db` 的 `publish_logs` / `chapters` / `cost_logs` 是最权威的账本；
- **恢复备份**：`backups/` 保留最近 3 份（sqlite3 backup API 生成，WAL 一致），
  恢复即复制最新备份覆盖 `demo.db` 后重启服务。

已知工程债（不影响当前运行）：frontmatter 解析器仍有几处复制、web_api 路由偏长、
n8n 质量门对正文截断无重试断言（max_tokens 已上调缓解）、前端 charts 分包后仍有
500KB 警告。

## 十六、已知限制与风险

- **番茄侧限制**：每天最多创建 1 本新书；每日提交字数上限约 9000+ 字（日更两章约 4400 字安全）；
  作品信息需过审才能发章节；Cookie 约 1-2 个月失效需重抓。
- **发布依赖**：`~/.n8n/.env` 的 Cookie/CSRF 与 n8n 工作目录绑定，n8n 必须从 `~/.n8n` 启动。
- **成本波动**：DeepSeek 单价与 token 用量变化会反映在 `cost_logs`，预算熔断兜底；
  日记/会议等 flash 调用计入成本，周会一次约几十次调用。
- **封面未全自动**：封面提示词自动生成，但出图与上传由用户在豆包 + 番茄后台完成。
- **测试数据**：`demo.db` 当前无作品（已清空旧书）；首次日更会从选题会结论或手动创建新书开始。
- **番茄 `chapter_number` 语义待核对**：算章节号按「返回值为当前最大章号 +1」处理；
  若真实 API 返回的本身就是下一章号，会产生跳号，需以真实登录态实测确认。
- **番茄接口真实上线前验证**：三步发布接口与建书接口目前只有开源实现交叉验证与本地
  测试，正式发布第一本前需用真实账号跑通一次。
- **PANEL_TOKEN 边界**：本机信任模型下的纵深防御；能伪造本机 Origin 头的本地进程
  无法被它阻止。
- **写手截断**：max_tokens 4000 缓解了截断，但 n8n 侧没有「结尾完整性」检测，若模型
  输出被截断且字数仍达标，会进入发布链（质量门只拦字数不足）。
- **番茄已发布但本地汇总中断**：直发章节的本地状态在「汇总运行结果 → 记录作品资料」
  才落库；若该阶段执行中断（n8n 崩溃/关机），番茄侧已发布而本地无记录，次日预检
  不会拦截（幂等按本地 published 计数），可能重复提交同序号章节。
- **数据库路径约定**：n8n 三份工作流的 executeCommand 固定使用 `demo.db`
  （相对 PIPELINE_ROOT）；`web_api --db 其他库` 只影响面板/专题会议，若使用其他库
  需同步修改工作流的 `--db` 参数保持一致。
- **当前书自动切换**：日更工作流通过「读当前书」节点从数据库取活跃作品
  （publishing/finishing 的最新一本），不再依赖 n8n 进程缓存的环境变量——
  自动建书/绑定后无需重启 n8n，日更即切到新书；`FANQIE_BOOK_ID` 仅作兜底。
- **8001 兼容实例**：8001 是历史保留的第二个面板实例（同一数据库，WAL 并发安全）；
  日常只使用 8000。
- **质量门降级放行**：读者审稿/主编终审节点异常（onError 容错生效）时按双审/单审
  降级，机械词表 + 字数 + 逻辑审稿通过即可发布（README 4.3 已如实说明）。
- **无活跃书时日更报错**：算章节号匹配不到当前书（未建书/绑定失效）会显式失败告警，
  不再静默取番茄账号第一本书。

## 十七、后续路线

### 已完成

- **完结机制**：ending_judge 周会输出 `finish_decision` → `apply_architect` 置
  finishing + 剩余章数 → publish_stock 收尾递减、完结停更并自动关闭日更 →
  新书孵化（finished 后创建下一本 planning）。
- **统一留痕（主体）**：audit_logs 全类别回填（预检/设置/操作/发布/会议/知识/建书/
  完结），前端「留痕档案」页可查；发布与质量门失败落 publish_logs。
- **人物卡进化**：record_work 每章写入 character_evolution（快照/变化/弧线），
  get_meta 注入写前记忆包，周会 `character_updates` 固化角色卡，前端作品库展示
  成长轨迹。

### 待做

- **guard 拦截意见细粒度入库**：守护细纲的 constraints / character_beats 目前只
  进写手提示词，未单独落库留痕（质量门失败已留痕，此项是守护层的审计补充）。
- **从会议结论一键创建新书**：新书选题会（无作品时）结论只存档到会议档案，
  不会直接生成 planning 新书；`next_book` 目前仅在本书 finished 后触发。
  目标：选题会结束后一键把结论转成新书，衔接「确认创意 → 自动建书」。

详见 `docs/evolution.md`（演进记录）与 `docs/planning/`（规划文档）。
