# M5 实施真元文档（无 AI 味深化 · N21 风格漂移检测）

## 总览

- **大阶段**：M7 质量深化扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N8/N9/N19/N20 已收口，N21 为下一 P1 候选）。
- **N21 一句话**：一条命令看全书章节的风格趋势——后半本有没有悄悄变味，量化到每一章。
- **现状**：
  - N20 `compute_style_profile`（句长 / 短句比 / 修饰密度 / AI 词命中）可复用为逐章画像；
  - N8 风格关键词语义（`extract_style_keywords` + 命中率）可复用；
  - N13 结构树（volume/chapter/section + draft_id + sort_order）与平铺草稿（latest version）可组合出「章节序列」；
  - 缺口：没有跨章节趋势视图；风格目前只按单稿检查（quality explain / consistency check），作者看不出「后半本悄悄变味」。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「多章作品 → style drift 输出逐章漂移分与趋势 → 明显变味的章节被标出」；既有 966 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **只报告不代笔**：drift 只输出报告；不自动改写、不改草稿状态、不落事件、不触发 proactive、不改风格锚点（继承 06 红线 4）。
2. **体裁自适应**：零草稿 / 单章 / 无有效正文输出空态 n/a，退出码 0，不报错；无结构树时用草稿创建时间兜底（继承 06 红线 5）。
3. **确定性可复现**：同一库同一时刻重复运行输出一致；全规则化计算，不调 LLM。
4. **基线透明**：基线 = 第一个可分析章节（首章定调）；维度口径、偏差公式、阈值全部写进本文档与 usage.md，不藏魔法数。
5. **全量章节可追溯**：逐章输出标题、指标与漂移分；禁忌词命中单独报告，不计入漂移分。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更；新增 core 模块 + CLI 子命令 + 测试。
- 复用 style_learn（compute_style_profile）、core.style（extract_style_keywords / get_style_anchor）、core.draft（get_draft_version / list_drafts）、core.structure（list_structure）、core.chat（get_workspace_or_raise），依赖方向 cli → core → quality/store 不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：风格漂移核心服务

### 做什么

- `core/style_drift.py`（新模块）：
  - **章节收集与排序**（内部函数 `_ordered_chapters`）：
    - 若结构树中存在 `kind == "chapter"` 且 `draft_id` 非空的节点：按 `list_structure` 的父先序取这些节点（同级已按 sort_order / created_at / id 稳定排序），标题用节点 title；未挂章节的草稿忽略。
    - 否则：全部草稿按 `created_at`、`id` 升序，标题用 `draft.title`（空则「未命名章节」）。
    - 每章正文 = 该草稿 `current_version` 的内容（`get_draft_version`）。
  - **逐章画像**：对每章正文调 `compute_style_profile([content])`；`total_chars == 0`（无有效句子）的章节跳过并计入 `skipped`。
  - **维度指标**（每章）：
    - `avg_sentence_len`、`short_sentence_ratio`、`modifier_per_1000`：直接来自 profile；
    - `ai_words_per_1000` = `len(profile.ai_word_hits) * 1000 / total_chars`（沿用 N20「词条命中一次」语义）；
    - `style_hits / style_total`：`extract_style_keywords(anchor.description)` 逐词 `kw in content`；无关键词时为 None / 0；
    - `forbidden_hits`：`anchor.forbidden_words` 按 `[,，]` 拆词、去空去重，逐词 `content.count` 求和（禁忌词只报告，不计入漂移分）。
  - **基线**：第一个可分析章节；其各维度偏差为 0。
  - **漂移分**（每个可用维度偏差 0–1，均值 × 100 四舍五入）：
    - `len_dev = min(1, |x-b| / max(b, 6.0))`
    - `short_dev = |x-b|`
    - `mod_dev = min(1, |x-b| / max(b, 1.0))`
    - `ai_dev = min(1, |x-b| / max(b, 0.5))`
    - `style_dev = |x-b|`（仅有关键词时参与）
    - `score = round(100 * mean(可用偏差))`；`DRIFT_THRESHOLD = 50`，`score >= 50` → `drifted`（基线章恒为 False）。
  - **DriftReport**（frozen dataclass，字段名以下为准）：
    - `chapters: list[DriftChapter]`（index 从 1 起；title；draft_id；avg_sentence_len；short_sentence_ratio；modifier_per_1000；ai_words_per_1000；style_hits: int|None；style_total: int|None；forbidden_hits: int；drift_score: int；drifted: bool）；
    - `baseline_title: str`（无基线时 ""）；
    - `skipped: int`；
    - `threshold: int`（= 50）；
    - `drifted: list[DriftChapter]`（仅 drifted=True 的章节）；
    - `verdict: str`（`"no chapters"` / `"need at least 2 chapters"` / `"style stable"` / `"drift detected in 1 chapter"`（N=1 单数）或 `"drift detected in N chapters"`（N≥2 复数），N 用英文数字）。
  - **只读**：不落事件、不写库、不触发 proactive；作品不存在抛 NovelError(NOT_FOUND)。
- tests（`tests/test_style_drift.py`）：结构与时间两种排序、未挂章节忽略、各维度数值、漂移分公式与阈值边界（49/50）、无风格关键词时维度剔除重归一、禁忌词拆分与计数、空正文章节跳过、零章/单章/全空 n/a、确定性、只读断言（events 数不变）、作品不存在 NOT_FOUND。

### 做到什么程度

- 风格漂移报告可复现；CLI 不接。

### 验收标准

- 单测覆盖上述全部路径；错误路径正确。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（S2）、文档（S3）、基线参数化 / 池化基线 / 移动基线、逐句定位、自动统一风格。

## 子阶段 S2：CLI 与端到端

### 做什么

- `cli/style.py` 新增 `style drift <workspace_id>`：
  - 对齐 S1 verdict 单复数：`drift detected in 1 chapter`（N=1）与 `drift detected in N chapters`（N≥2），并同步修正 tests/test_style_drift.py 中 verdict 断言（允许触碰 core/style_drift.py 的 verdict 生成与 tests/test_style_drift.py）；
  - 结构挂章的 draft_id 悬空（草稿不存在）时跳过该章并计入 `skipped`，不让单个坏节点炸掉整份报告（S1 独立审查 P3 意见；允许触碰 core/style_drift.py 的 `_ordered_chapters` 与 tests/test_style_drift.py）；
  - `skipped > 0` 时输出 `skipped chapters: N` 行（放在逐章行之前），提示存在未分析的章节；
  - 输出格式（字段名与单位固定）：
    ```text
    chapters: 3
    baseline: 第一章 雨夜
    1 第一章 雨夜: len 9.2 / short 62.0% / mod 1.2 / ai 0.0 / style 3/3 → drift 0
    2 第二章 线索: len 10.5 / short 58.0% / mod 2.1 / ai 0.8 / style 3/3 → drift 18
    3 第三章 转折: len 15.8 / short 40.0% / mod 3.5 / ai 1.2 / style 1/3 → drift 67
    drift trend: 0 / 18 / 67
    drifted chapters: 第三章 转折（67）
    forbidden hits: 第三章 转折: 2（窒息、璀璨）
    verdict: drift detected in 1 chapter
    ```
    - 无风格关键词时行内省略 `style x/y`；无禁忌词命中时不输出 `forbidden hits:` 行；无漂移章时不输出 `drifted chapters:` 行。
    - 空态：无草稿 → `no chapters`；仅 1 章（或 0 可分析）→ `chapters: N` + `drift: n/a (need at least 2 chapters)`；退出码均 0。
  - 退出码：作品不存在 → NOT_FOUND → 1（CLI 既有映射）。
- tests：
  - registry 的 style 组补 drift；
  - 端到端「3 章作品（结构挂章优先）+ 风格锚点 + 禁忌词 → 逐章行、trend、drifted chapters、forbidden hits、verdict」；
  - 无结构时按创建时间排序；无关键词维度剔除；空态两种；作品不存在 1；确定性（两次输出一致）；只读（events list 不变）。

### 做到什么程度

- 作者一条命令看到全书风格趋势；报告只读。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 基线参数（`--baseline`）、趋势图输出、面板集成（N12 另拆）。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- usage.md 补 `style drift` 小节：命令、章节排序规则、基线口径、五个维度偏差公式、阈值 50、禁忌词单独报告、空态；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260821-M5N21S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 966+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 基线池化 / 移动基线、面板展示、N22 好句识别联动。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-21）：实施文档就绪，用户授权低价窗口内自主推进，拆包 S1。
