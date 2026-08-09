# Skill 包整合说明（2026-08-10）

本轮把七个公开的 AI 网文写作 skill 包抓回本地精读后，把其中最值钱的机制融进了
n8n 日更流水线（`n8n/novel_workflow.json`）和 Python 数据层。

## 调研来源

抓取副本保存在 `docs/research/skills/raw-*`（源码来自各仓库 main/master，仅供内部研究）：

| 包 | 仓库 | 主要吸收点 |
| --- | --- | --- |
| oh-story-claudecode | worldwonderer/oh-story-claudecode | 情绪先行、章节钩子体系、追踪文件（角色状态/伏笔/时间线）、去 AI 味脚本 |
| sumeru | xindoo/sumeru | 选题→世界观→大纲→写作→审查→润色→完稿的分模块编排、三阶段审查修复 |
| humanizer-zh | ai-zixun/humanizer-zh | 中文去 AI 味核心规则（翻译腔/空泛大词/机械结构/标点） |
| zaomeng | wkbin/zaomeng | 人物档案蒸馏、OOC 红线、关系映射、证据纪律 |
| ai-novel-writing-skills | imerzzhu/ai-novel-writing-skills | Codex 版九个技能，结构与 sumeru 同源，取细纲驱动写作 |
| Chinese-WebNovel-Skill | Tomsawyerhu/Chinese-WebNovel-Skill | 选材六问、先搭结构再铺正文、去 AI 味是硬约束 |
| chinese-webnovel-skills | tance-mang/chinese-webnovel-skills | 同类方法论交叉验证 |

## 已融入流水线的机制

### 1. 故事圣经增量更新（Planner出大纲 / 解析大纲）

- Planner 输出里新增 `bible`：`world_rules`（世界观/力量体系规则）、`characters`
  （含 personality / speech_style / ooc_redline / current_state）、`relationships`、
  `style_guide`。
- 已有圣经非空时，Planner 被要求「沿用 + 增量补充，不得另起炉灶」。
- `解析大纲` 新增 `mergeBible`：角色按名字合并、关系去重、规则取并集，旧书数据
  不会因为新一次规划被推倒。

### 2. 写手拿到人物卡（写手A/B）

- 写手提示词现在注入：出场角色卡、人物关系、世界观规则、本章情绪目标、章节定位、
  需要回收的伏笔、需要埋设的伏笔。
- 硬性要求：人物口吻可区分、禁止 OOC、世界观不得吃书、伏笔自然埋/收。

### 3. 去 AI 味前移（写手 + 润色）

按 humanizer-zh 与 oh-story 的规则合并成硬约束：

- 禁止词：突然（≤1）、这一刻/就在这时开头、不由自主、情不自禁、微微一愣、
  缓缓说道、一股强大的气息、与此同时。
- 翻译腔句式：不是…而是…、对于…来说、基于、使得、值得注意的是。
- 不用长破折号「——」；冒号每段≤1；删空泛大词与口号化收束；不连续排比；
  列表能改叙述就改叙述；输出前默读检查。

### 4. 审稿升级为六类底线检查（审稿A/B）

在原有风格/节奏/标点/衔接检查之外，新增：

- 时间线矛盾
- 设定崩坏（与世界观规则冲突）
- 人物 OOC（对照角色卡）
- 重复情节
- 信息泄露（角色知道不该知道的信息）
- 伏笔死结（埋了不收或回收突兀）

`passed` 要求：无 critical、无底线问题、major≤1 且 score≥7。

### 5. 每章记忆沉淀（提炼剧情A/B → 整理剧情A/B）

质量门通过后、排版前新增两个节点，逐章从正文提取：

- `summary`：本章核心剧情
- `character_updates`：角色状态变化
- `plot_events`：事件（foreshadow/setup/resolve/world/item/character）
- `foreshadowing_planted` / `foreshadowing_recovered`：伏笔台账增删
- `next_hook`：下一章必须承接的悬念

`汇总运行结果` 把这些写进 `payload.outline.bible` 与每章 `summary/ending_excerpt`，
`record_work.py` 落库：伏笔表新增 `description` 列（含迁移），回收时按描述关闭
对应开放伏笔；角色状态回写 `characters.state`。

### 6. 前端展示圣经

作品详情面板新增「角色卡 / 人物关系 / 世界观规则」三行，直接展示 `outline.bible`。

## 验证

- `tools/archive/test_record_work.py`：临时库验证伏笔登记/回收、角色状态回写、摘要落库。
- `tools/get_meta.py`：确认记忆包输出 bible、伏笔（含描述）、角色状态。
- 提示词冒烟测试：`tools/archive/test_skill_prompts.py` 逐节点调用 DeepSeek 验证 JSON
  可解析（见该脚本，需 `~/.n8n/.env` 的 DEEPSEEK_API_KEY）。

## 未纳入 / 保留给后续

- oh-story 的拆文库/对标库体系：需要持续爬榜 + 拆文，目前只做方法论吸收，未建对标库。
- sumeru 的批量子 Agent 并行写作：n8n 日更两章规模不需要，保留给未来长篇重写。
- zaomeng 的 60+ 字段人物档案：对自动日更过重，只取浓缩版角色卡。
- 封面生成、热度爬虫（oh-story 的 fanqie-rank-scraper.js）留作下一步独立接入。
