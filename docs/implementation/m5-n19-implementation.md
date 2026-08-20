# M5 实施真元文档（无 AI 味深化 · N19 一致性自动核查）

## 总览

- **大阶段**：M7 质量深化扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N8/N9 已收口，N19 为 P1 无 AI 味深化候选之一）。
- **N19 一句话**：审稿自动对照设定库与伏笔核查正文——人名、时间线、伏笔咬合，长文一致性不用人肉盯。
- **现状**：
  - 设定库（N5）：SettingEntry（kind=character/timeline/world 等、name、content、current_version）；
  - 伏笔（U20）：PlotThread（kind=foreshadow/goal/hook、content、status、chapter）；
  - 正文版本（DraftVersion）；审稿已有「一致性优先」立场（N2）与主动提醒（N1 proactive_consistency）；
  - 没有自动核查服务；N19 是规则化第一版，不引入语义模型。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「设定库（人物名 + 时间线数字）+ 开放伏笔 + 含矛盾的正文 → consistency check 输出冲突 / 未提及 / 出现统计 → 全程只读不代笔、退出码 0 → 无设定无伏笔时输出干净空态」；既有 892 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **只报告不代笔（06 红线 4 继承）**：核查只输出报告，不自动改写正文、不自动退稿、不改变草稿状态、不绕过审稿/作者判断。
2. **纯只读**：核查不写任何数据——不落事件、不留业务痕迹、不改配置；重复执行结果一致（确定性规则）。
3. **不阻塞**：核查不构成任何创作前置；缺设定 / 缺伏笔 / 无正文均为合法输入（空态或明确用法错误，不崩溃）。
4. **口径可复现**：人物出现、数字冲突、伏笔提及全部用确定性规则（见 C1），相同输入输出一致；避免过度设计：规则只抓「显式可判」的矛盾，宁可漏报不误报。
5. **体裁自适应**：不假设章节结构；任意正文（短篇/长篇/单章）都可核查。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更；新增 core 模块 + CLI 命令组 + 测试。
- 复用既有 list_settings / list_threads / get_draft_version / 分词与数字提取辅助，依赖方向 cli → core → store 不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 C1：规则化核查核心服务

### 做什么

- `core/consistency.py`（新模块）：
  - `ConsistencyIssue`：kind（character_missing / number_conflict / thread_missing）、severity（info / conflict）、setting_name（str）、detail（str）、sentence（int | None，1-based 句号，无则 None）；
  - `ConsistencyReport`：issues（list）、settings_checked（int）、threads_checked（int）、character_mentions（dict[str, int]，设定人物名 → 正文出现次数）；
  - `check_consistency(db, workspace_id, text) -> ConsistencyReport`（text 空白 → NovelError(USAGE_ERROR)）：
    1. 人物核查：对 kind=character 的设定（当前版本），统计 entry.name 在正文中的出现次数；出现 0 次 → issue（character_missing，severity=info，detail 注明「设定人物未在正文出现」）；
    2. 数字冲突：对 timeline/world/character 设定条目，从其 content 提取「数字 + 单位」对（阿拉伯数字、中文数字，归一为逻辑值；单位词：点/时/分/年/月/日/岁/号 等），按单位汇总为设定值集合；对正文逐句提取同类「数字 + 单位」对；若某句含该条目主题词（entry.name，以及 content 中「：」前的主题词，如有）且该单位下存在正文值不在设定值集合中 → issue（number_conflict，severity=conflict，detail 示例：正文「十三点」不在设定值中（设定含：十一点、十二点）（句 2））；同一句同一单位同一逻辑值（中文/阿拉伯写法不同）只报一次，detail 保留该值首次出现的写法；
    3. 伏笔核查：对开放状态（planted/pending）的 PlotThread，从其 content 提取关键词（实现二选一并写明：content 的 2–4 字 ngram 集合 或 去除标点后的词元；建议 ngram 更稳），正文命中任一关键词 → 提及；零命中 → issue（thread_missing，severity=info）；
    4. 排序：conflict 优先，其余按设定/伏笔原始顺序；空设定+空伏笔 → 空 issues（CLI 输出空态）。
- tests（tests/test_consistency.py）：人物出现/缺失、数字冲突（同单位不同值、同值不报、不同单位不报、无主题词不报）、伏笔命中/未提及、空设定空伏笔、空白正文 usage error、确定性（两次一致）、既有 892 测试不回归。

### 做到什么程度

- 规则化核查可复现；只读不落库；漏报优先（不误报）。

### 验收标准

- 单测覆盖上述全部路径；空白正文错误路径正确。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（C2）、语义级矛盾检测（同义改写/指代消解，后续按需）、跨章节全文扫描聚合（可后置）。

## 子阶段 C2：CLI 与端到端

### 做什么

- `cli/consistency.py`（新命令组）`consistency check <草稿ID>`：
  - 读草稿最新版本正文 + 作品设定库与开放伏笔 → 输出报告；
  - 输出格式（示例）：
    - `settings checked: N / threads checked: M`；
    - 每问题一行：`[冲突] 旧车站：正文「十二点」不在设定值中（设定含：十一点）（句 3）` / `[未提及] 沈夜：设定人物未在正文出现` / `[未提及] 伏笔·黑伞人：关键词未出现`；
    - 人物出现统计（有命中时）：`[人物] 沈夜：出现 3 次`；
    - 干净：`no consistency issues found`；
  - 退出码：0（含有问题，报告性命令不失败）；草稿不存在 / 空白正文 → 既有错误映射（1 / 2）；
  - 全程只读，不落事件、不改状态。
- tests：端到端「有设定+伏笔+矛盾正文 → 输出冲突/未提及/统计 → 退出码 0 → 干净文本空态 → 草稿不存在 1」；registry 补 consistency 组。

### 做到什么程度

- 作者/审稿一条命令拿到可读的一致性报告；只报告不代笔。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 自动退稿 / 改写建议落库（红线 1）、跨作品聚合接入（N10 overview 可后置扩展）。

## 子阶段 C3：文档、全量回归与收口

### 做什么

- usage.md 补 `consistency check` 小节：命令、输出格式、检测口径（人物出现 / 数字冲突 / 伏笔提及）、只报告不代笔红线、空态；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260820-M5N19C1 / C2 / C3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 892+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 跨章节一致性趋势（N21 风格漂移另拆）、自动修正（红线 1）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 收口（2026-08-21）：C1（d0ab642 + a1da381 + 053aa81）、C2（431d6fb）、C3（usage.md）全部完成并独立审查收敛；全量 924 测试、smoke_m3、stress_m3 全绿；审查链归档 docs/reviews/20260820-M5N19C1-initial.md / 20260820-M5N19C1-fix.md / 20260820-M5N19C1-fix2.md / 20260820-M5N19C2-initial.md / 20260820-M5N19C3.md。N19 正式收口。
