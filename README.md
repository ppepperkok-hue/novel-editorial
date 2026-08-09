# novel-pipeline

AI 网文自动生成与发布流水线：n8n 定时编排 + DeepSeek 多 Agent 协作 + Python
记忆层（SQLite）+ 番茄小说发布 + 零依赖监控面板。

目标场景：**每天 08:00 自动生成两章并提交番茄审核**，月预算 100 元内，全程无人值守；
出现 Cookie 失效、预算超限、重复触发等情况会自动熔断并写告警。

## 一、整体架构

```text
[n8n 日更工作流]                     [n8n 架构师周会（周日 08:10）]
 每日 08:00 触发                       读圣经/摘要/伏笔/完读率/热点
  └─ 备份 → 预检 → 9 Agent 协作         └─ 输出蓝图增量/读者画像/卷目标
        │                                    └─ 落库（日更自动消费）
        ├─ 生成（Planner/守护/写手/编辑/审稿×2/终审/记忆官）
        └─ 发布（建草稿→保存→提交→复核→记录）→ 采集完读率
                              │
                              ▼
            SQLite（圣经/章节/伏笔/角色/成本/发布日志）
                              │
                              ▼
            监控面板 http://127.0.0.1:8000（5 秒轮询）
```

## 二、多 Agent 协作矩阵（9 类角色）

| Agent | 节点/工作流 | 模型 | 职责 |
| --- | --- | --- | --- |
| 策划官 | Planner出大纲 | pro | 生成/增量更新故事圣经与两章细纲（情绪/定位/伏笔埋收） |
| 世界观守护 | 守护细纲 → 解析守护 | flash | 动笔前拦截 OOC/吃书/时间线/伏笔矛盾，输出 constraints 与 character_beats |
| 叙事写手 | 写手A/B | pro | 按细纲+角色卡+守护约束写 2000 字正文 |
| 文字编辑 | 润色A/B | flash | 去 AI 味、翻译腔、标点、节奏收紧 |
| 逻辑审稿 | 审稿A/B | flash | 六类底线问题（时间线/设定/OOC/重复/信息泄露/伏笔死结） |
| 读者体验审稿 | 读者审稿A/B | flash | 追读欲/钩子/情绪满足评分 |
| 主编终审 | 主编终审A/B | flash | 仲裁两审冲突，输出 verdict 与 must_fix |
| 记忆官 | 提炼剧情A/B → 整理剧情A/B | flash | 提取摘要、角色状态、事件、伏笔台账 |
| 架构师 | 架构师周会（独立工作流） | flash | 未来蓝图增量、读者画像、卷目标微调 |

协作要点：

- **B 章串行承接 A 章**：写手B 输入 A 章结尾原文 + A 章提炼（next_hook），
  审稿B 核对开篇承接；两章不再是独立孤岛。
- **双审 + 终审**：逻辑审稿与读者审稿意见冲突时由主编终审裁决（底线问题优先，
  读者意见进 must_fix）；质量门要求 `verdict === 'pass'` 且机械检查通过。
- **守护只输出约束不直接改稿**：失败降级为空约束，不阻断日更。
- **记忆闭环**：每章发布前提取记忆写回 SQLite，次日记忆包自动带上
  （上一章结尾/角色状态/伏笔/热点/角色卡）。

## 三、日更工作流（55 节点）

```text
每日触发(08:00)
  → 备份数据库（保留最近 3 份）
  → 预检（Cookie 实测 / 当日幂等 / 月度预算 100 元熔断）
  → 查章节号 → 读本地资料（记忆包）→ 生成/解析作品资料
  → Planner出大纲 → 守护细纲 → 解析守护
  → 写手A → 润色A → 审稿A → 读者审稿A → 主编终审A → 质量门A
  → 提炼剧情A → 整理剧情A
      ├─ 排版A → 新建草稿A → 保存内容A → 提交发布A → 校验发布A → 复核发布A
      └─ 写手B → 润色B → 审稿B → 读者审稿B → 主编终审B → 质量门B
         → 提炼剧情B → 整理剧情B → 排版B → 新建草稿B → ... → 复核发布B
  → 汇总运行结果（含成本 token 台账）→ 记录作品资料 → 采集阅读数据
```

失败容错：质量门/校验/复核不再抛错；失败分支在排版处短路，另一章照常发布；
失败原因写入 `chapters[].error`；发布后经 chapter_list 复核为
`published / pending` 两种真实状态。

## 四、数据层（SQLite）

- `novels`：书名/简介/标签/主角/大纲（内含 **bible**：世界观/角色卡/关系/文风/
  金手指/读者画像；**blueprints**：章节蓝图）
- `chapters` + `chapter_summaries`：章节正文元数据与逐章记忆
- `characters`：角色状态快照（每章更新）
- `plot_threads`：伏笔台账（埋设章/回收章/描述/状态）
- `cost_logs`：LLM token 用量与折算成本（月度汇总/熔断依据）
- `publish_logs` / `quality_reports`：发布与质量审计

## 五、安全与加固

- n8n 仅监听 `127.0.0.1`（`N8N_LISTEN_ADDRESS`），管理员密码已强化
- 所有凭据在 `~/.n8n/.env`，仓库不存密钥；`.gitignore` 排除 demo.db/备份/第三方参考
- 每日自动备份数据库；Cookie 失效/预算超限自动熔断并写 `alerts.log`
- LLM JSON 输出容错解析；A/B 分支相互隔离，不会因单章失败丢记录

## 六、快速开始

```bash
pip install -e .

# 1. 配置 ~/.n8n/.env（见 .env.example）
# 2. 启动监控面板
python -m novel_pipeline.web_api --db demo.db --port 8000
# 3. 导入/更新 n8n 工作流：n8n/novel_workflow.json、n8n/architect_weekly.json
# 4. 测试
python run_tests.py
```

详细运维说明（番茄发书流程、已知限制、成本单价调整）见
[n8n/README.md](n8n/README.md)；架构决策见 [ARCHITECTURE.md](ARCHITECTURE.md)；
多 Agent 与审查记录见 [docs/research/multiagent-and-audit.md](docs/research/multiagent-and-audit.md)。

## 七、环境变量

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek 密钥（n8n 与脚本共用） |
| `FANQIE_COOKIE` / `FANQIE_CSRF_TOKEN` | 番茄作者后台登录态（约 1-2 个月失效） |
| `FANQIE_BOOK_ID` / `FANQIE_VOLUME_ID` / `FANQIE_VOLUME_NAME` | 作品与分卷 ID |
| `MONTHLY_BUDGET` | 月度成本预算（默认 100 元） |
| `COST_PRO_PER_1K` / `COST_FLASH_PER_1K` | LLM 单价（元/千 token），用于成本台账 |
| `N8N_HOST` / `N8N_LISTEN_ADDRESS` | n8n 主机名与监听地址 |
