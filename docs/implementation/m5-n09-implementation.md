# M5 实施真元文档（无 AI 味深化 · N9 质量门语料校准）

## 总览

- **大阶段**：M7 质量深化（backlog 见 docs/project-plan/06-new-capability-backlog.md，N8 → N9）。
- **N9 一句话**：「无 AI 味」不拍脑袋——作者拿自己的真实语料跑一次校准，得到有依据的阈值建议。
- **现状**：
  - F15 质量门已落地：得分 = AI 味词命中×6 + 修饰词命中×3 + 句式重复×4 + 风格罚分；默认阈值 8，可经 `NOVEL_QUALITY_THRESHOLD` 或 config.toml `[defaults] quality_threshold` 调整。
  - 阈值与词表是初版，多个立项文档（project-checklist、03-core-goals、m3-verification）都写明「随真实语料迭代校准」是既定约束。
  - 没有语料读取、分布统计或阈值建议设施；config.toml 目前只读（tomllib），无写回机制。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「作者提供一组真实文本语料 → quality calibrate 输出每样本维度统计 + 分数分布 + 建议阈值 → --apply 幂等写入 config.toml → 后续 quality check 使用新阈值」；语料内容不落库。

## 红线（本阶段强制，06 通用性红线继承）

1. **语料只读不落库**：校准只读用户提供的文本文件，语料内容绝不写入 data/、不写入事件、不写任何数据库；命令本身不产生业务留痕。
2. **不静默改阈值**：默认只输出统计与建议；只有显式 `--apply` 才写入 config.toml，写入前打印将写入的值；重复执行结果一致（幂等）。
3. **建议口径可复现**：分布统计与建议阈值基于确定性排序算法，相同语料重复运行输出一致；空语料 / 无有效文本文件时报业务错误（退出码 1），不输出无意义的建议。
4. **不改变既有行为**：不引入语料时，quality check / draft generate / draft revise 行为与默认阈值完全不变；config.toml 未写时不生效。
5. **体裁自适应**：校准对任意文本（短篇、长篇、同人、网文）通用，不假设章节目录或结构；单个文件即一个样本。

## 地基影响评估（先评估再动工）

- 无表结构变更、无事件契约变更、无新依赖；新增 core 模块 + CLI 子命令 + 测试。
- config.toml 写回需要最小文本级机制（保留注释与其他键，只替换/新增 `[defaults] quality_threshold`），属 Q2 范围。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，或必须引入新依赖，先停下回报，不硬做。

## 子阶段 Q1：语料读取与分布统计核心服务

### 做什么

- `core/calibration.py`（新模块）：
  - `scan_corpus(path) -> CorpusReport`：读取一个目录（递归）或单个文本文件中的 `.txt` / `.md` 样本（每文件一个样本；隐藏文件与空文件跳过）；
  - 每个样本用 `check_quality`（默认词表与修饰词表，不接风格锚点）计算：文件路径、字数、ai_word_hits 数、modifier_hits 数、sentence_repetition 数、score；
  - `CorpusReport`：samples（list，按路径排序）、scores 分布统计（min / median / p90 / p95 / max，分数排序后确定性计算）、建议阈值 `suggested_threshold`；
  - 建议口径：`suggested_threshold = max(1, ceil(p90_score))`；语料为空或无有效样本时抛 NovelError（CALIBRATION 类错误，复用既有错误码枚举，若无合适枚举停下回报）。
- tests：多文件样本统计、单文件、隐藏/空文件跳过、p90 边界（含全零分语料 → 建议 1）、空目录报错、确定性（两次运行一致）。

### 做到什么程度

- 核心统计可复现；分布与建议有单测覆盖；不接 CLI。

### 验收标准

- 单测覆盖上述全部路径；空语料错误路径正确；既有 830 测试全绿。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（Q2）、config.toml 写回（Q2）、带标注的坏样本评分（N23 试读反馈回流另拆）。

## 子阶段 Q2：CLI 与 config 写回

### 做什么

- `cli/quality.py` 新增 `quality calibrate <语料路径> [--apply]`：
- 默认输出：样本数、每样本一行（路径、字数、AI 词/修饰词/句式重复命中、score）、分布摘要（min / median / p90 / p95 / max）、建议阈值行 `suggested threshold: <N>`；
  - 退出码口径与既有错误码映射一致：路径不存在 → NOT_FOUND → 退出码 1；空语料 / 无有效样本 → USAGE_ERROR → 退出码 2；
  - `--apply`：先打印 `apply: quality_threshold = <N>`，再幂等写入 config.toml（`[defaults]` 段下 `quality_threshold = <N>`；文件不存在则创建，存在则保留注释与其他键只替换/新增该键）；写入后打印确认行；
  - 无 `--apply` 时绝不写文件。
- tests：端到端「语料目录 → 输出统计与建议 → --apply 写入 config.toml → 重复 --apply 幂等 → load_settings 读出新阈值」；不 --apply 不写文件；空语料退出码 2、路径不存在退出码 1；registry 补 quality calibrate。

### 做到什么程度

- 作者一次命令拿到「阈值建议 + 可选落配置」；config 写回可复现、可回退（手动删键即恢复默认）。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 词表校准（词表本身不因语料自动增删）、风格维度校准（N20 文风参考学习另拆）、自动定期校准。

## 子阶段 Q3：文档、全量回归与收口

### 做什么

- docs/usage.md「质量门」节补 `quality calibrate` 小节：语料格式（目录/单文件、.txt/.md）、输出说明、建议口径（p90 向上取整、最低 1）、`--apply` 写回与幂等、只读不落库红线；示例 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260820-M5N09Q1 / Q2 / Q3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 830+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- N23 试读反馈回流（N9 收口后按 backlog 另拆）、面板集成。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-20）：实施文档就绪，用户授权低价窗口内自主推进，拆包 Q1。
