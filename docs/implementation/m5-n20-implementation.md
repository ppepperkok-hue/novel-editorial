# M5 实施真元文档（无 AI 味深化 · N20 文风参考学习）

## 总览

- **大阶段**：M7 质量深化扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N8/N9/N19/N20 已收口，N21 为下一 P1 候选）。
- **N20 一句话**：给几段自己喜欢的文本，风格锚点从语料里长出来——风格描述不再靠抽象词。
- **现状**：
  - 风格锚点（F14）：description（如「平实克制短句」）+ forbidden_words，`style set / style show` 已有；
  - 语料读取（N9）：calibration 的 CORPUS_EXTENSIONS / is_valid_corpus_file / read_sample（UTF-8-sig、隐藏/空文件跳过语义）可复用；
  - 质量门（F15）：DEFAULT_MODIFIERS / DEFAULT_AI_WORDS / split_sentences 可复用；
  - 没有从参考语料提取风格特征的入口；风格描述目前全靠作者手写。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「参考语料（短句、低修饰密度）→ style learn 输出画像（句长 / 短句占比 / 修饰密度 / AI 味词提示）与建议风格描述 → --apply 写入风格锚点 → style show 可见 → 不 --apply 不写」；既有 924 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **不静默覆盖**：默认只输出画像与建议描述；只有显式 `--apply` 才写入风格锚点 description（写入前打印将写入内容），与 N9 calibrate 语义一致；重复执行结果一致（确定性）。
2. **语料只读不落库**：参考语料只读，内容不写入 data/、不落事件、不产生业务留痕；--apply 只更新风格锚点 description（不动 forbidden_words、不动其他作品）。
3. **建议是起点不是判决**：建议描述是规则化模板产物，作者仍可用 `style set` 覆盖；AI 味词命中只作提示，不自动把词塞进 forbidden_words。
4. **口径可复现**：句长、短句占比、修饰密度全部确定性计算，相同语料重复运行输出一致；空语料 / 无有效文本报用法错误（复用 N9 语义）。
5. **体裁自适应**：任意文本（短篇/长篇/同人/网文）可学习；不假设章节结构。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更；新增 core 模块 + CLI 子命令 + 测试。
- 复用 calibration（语料读取）、quality.gate（split_sentences / DEFAULT_MODIFIERS / DEFAULT_AI_WORDS）、core.style（set_style_anchor），依赖方向 cli → core → quality 不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：风格画像与建议描述核心服务

### 做什么

- `core/style_learn.py`（新模块）：
  - 复用 `novel_editorial.core.calibration` 的 `is_valid_corpus_file` / `read_sample` / `CORPUS_EXTENSIONS`；
  - `collect_corpus_texts(path) -> list[str]`：目录递归或单文件，非隐藏 `.txt/.md`，去空白后为空跳过；无有效样本抛 NovelError(USAGE_ERROR)（路径不存在 NOT_FOUND，与 N9 口径一致）；
  - `StyleProfile`（frozen dataclass）：samples（int）、total_chars（int，去空白）、avg_sentence_len（float，去空白字数 / 句数，复用 split_sentences）、short_sentence_ratio（float，≤15 字句占比）、modifier_per_1000（float，DEFAULT_MODIFIERS 命中数 / 千字）、ai_word_hits（list[str]，DEFAULT_AI_WORDS 命中去重排序）；
  - `compute_style_profile(texts: list[str]) -> StyleProfile`（纯函数，确定性）；
  - `build_suggested_description(profile) -> str`：确定性规则模板，至少区分：
    - 句长：avg ≤ 12 →「短句」；12–18 →「句子不长」；>18 →「长句较多」；
    - 短句占比 ≥0.5 →「节奏快」；0.3–0.5 →「长短句相间」；<0.3 →「句子舒展」；
    - 修饰密度 ≤5/千字 →「修饰克制」；>5 →「修饰偏多」；
    - 拼装为逗号分隔的描述（如 `短句，节奏快，修饰克制`），可直接作 description 使用。
- tests（tests/test_style_learn.py）：语料收集（目录/单文件/隐藏/空/无有效样本报错）、画像各维度数值、建议描述各分支、确定性、AI 味词提示列表、既有 924 测试不回归。

### 做到什么程度

- 风格画像与建议描述可复现；CLI 不接。

### 验收标准

- 单测覆盖上述全部路径；空语料错误路径正确。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（S2）、文档（S3）、语义级风格向量（后续按需）。

## 子阶段 S2：CLI 与端到端

### 做什么

- `cli/style.py` 新增 `style learn <作品ID> <语料路径> [--apply]`：
  - 输出：`samples: N`、`avg sentence length: X 字`、`short sentence ratio: Y%`、`modifier per 1000 chars: Z`、AI 味词命中非空时 `ai words in corpus: A、B`（stderr 或 stdout 提示均可，选 stdout 更可断言）、`suggested description: <描述>`；
  - `--apply`：先打印 `apply: description = <描述>` → set_style_anchor(description=建议描述, forbidden_words=现有值不变) → 打印 `style anchor updated: <作品ID>`；无 `--apply` 绝不写；
  - 退出码：路径不存在 → NOT_FOUND → 退出码 1；空语料 / 无有效样本 → USAGE_ERROR → 退出码 2（与既有错误码映射一致）；作品不存在 1。
- tests：端到端「短句低修饰语料 → 画像与建议 → --apply 写入 → style show 显示 → 重复 --apply 幂等 → 不 --apply 不写 → 空语料 2」；registry 的 style 组补 learn。

### 做到什么程度

- 作者一条命令拿到可落地的风格描述建议；不静默覆盖。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 语料自动进 forbidden_words、批量风格模板（N26 另拆）。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- usage.md 补 `style learn` 小节：命令、画像口径（句长 / 短句占比 / 修饰密度 / AI 味词提示）、建议描述规则、--apply 语义与不静默覆盖红线、空态；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260821-M5N20S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 924+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 风格漂移检测（N21 另拆）、好句识别（N22 另拆）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 收口（2026-08-21）：S1–S3 全链完成；六份审查/复核报告归档 docs/reviews/20260821-M5N20*；966 测试全绿，smoke_m3 / stress_m3 通过。
