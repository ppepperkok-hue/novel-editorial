# M5 实施真元文档（质量深化 · N23 试读反馈回流）

## 总览

- **大阶段**：M7 质量深化扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N8/N9/N19/N20/N21/N22 已收口，N23 为下一 P2 候选）。
- **N23 一句话**：试读者的批注与评分进入质量校准——「无 AI 味」不再只靠内置词表，也有真实读者反馈。
- **现状**：
  - N9 `quality calibrate` 已能从真实语料建议阈值（nearest-rank p90、向上取整、最低 1），但语料没有「好坏标注」；
  - 缺口：试读者的判断进不了校准，质量门无法对齐真人反馈。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「带标注 JSONL（坏样本高分 + 好样本低分）→ `quality feedback` 输出分位数 / 当前阈值一致率 / 建议阈值 → `--apply` 写入 config 且幂等 → 无 `--apply` 不写」；既有 1100 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **反馈只读除非 --apply**：`quality feedback` 默认只报告；仅 `--apply` 写 config（复用 `set_quality_threshold`，幂等）。
2. **不落库不落事件**：批注不写数据库、不落事件、不触发 proactive——反馈是校准输入，不是作品数据。
3. **口径可复现**：分数复用 `check_quality`；分位数与建议阈值复用 N9 语义（nearest-rank、p90 向上取整、最低 1）；相同输入重复执行输出一致。
4. **标注是参考不是判决**：建议阈值与一致率只是报告，作者保留最终阈值；建议阈值 = 在候选阈值（分数跨度内的整数网格 `floor(min_score)` 到 `ceil(max_score)`，∪ 当前阈值）上最大化标注一致率的整数阈值，并列时取更高阈值（更保守），无 bad 样本时不建议、`--apply` 拒绝。
5. **多行文本支持**：标注文件用 JSONL（每行一条 `{"label": "bad"|"good", "text": "..."}`，text 可含换行），格式错误逐条指出（USAGE_ERROR）。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增（复用 quality_threshold）、无事件契约变更、无新依赖。
- 新增 `core/feedback.py` + `cli/quality.py` 追加 `quality feedback` 子命令 + 测试；依赖方向 cli → core → quality 不变。
- 统计口径与 `core.calibration` 的 nearest-rank 分位一致（可提取公共函数，或按文档口径在 feedback 模块实现，不复制业务语义之外的逻辑）。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：反馈解析与分析核心服务

### 做什么

- `core/feedback.py`（新模块）：
  - `@dataclass(frozen=True) FeedbackSample`：label（"bad" / "good"）、text、line（源文件行号，便于报错）。
  - `load_feedback_samples(path) -> list[FeedbackSample]`：JSONL 解析；路径不存在 → NOT_FOUND；逐行校验（合法 JSON、label ∈ {bad, good}、text 去空白非空），任一不符 → USAGE_ERROR（消息含行号）；空文件 / 无有效样本 → USAGE_ERROR。
  - `@dataclass(frozen=True) FeedbackReport`：samples / bad_count / good_count / bad_stats（min、median、p90、max）/ good_stats / threshold_used / agreement（当前阈值一致率）/ suggested_threshold（int | None）/ suggested_agreement（float | None）。
  - `analyze_feedback(samples, threshold) -> FeedbackReport`：逐样本 `check_quality(text).score`；bad 判为 score > threshold；一致率 = 标注与门判定相符比例；**建议阈值 = 分数跨度内整数网格（`floor(min_score)` 到 `ceil(max_score)`，∪ 当前阈值）上一致率最高的整数阈值，并列时取更高阈值（更保守），报告的一致性必须与建议阈值严格对应（不截断）**；无 bad 样本时 suggested_threshold / suggested_agreement 为 None；分位口径与 N9 一致（nearest-rank）。
- tests（`tests/test_feedback.py`）：JSONL 解析（含多行文本、空行跳过？定义：空行跳过，行首尾空白容忍）/ 坏标签 / 坏 JSON / 空文本 / 路径不存在 / 空文件；分析（bad/good 分位、一致率、建议阈值、无 bad 样本 None、阈值边界）、确定性、只读（不写库不落事件）。

### 做到什么程度

- 标注解析与反馈分析可复现；CLI 不接。

### 验收标准

- 单测覆盖上述全部路径；口径与 N9 一致可断言。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（S2）、文档（S3）、批注入库、多读者聚合、实时反馈流。

## 子阶段 S2：CLI 与端到端

### 做什么

- `cli/quality.py` 新增 `quality feedback <标注文件> [--apply]`：
  - 输出：
    ```text
    samples: 12
    bad: 8 / good: 4
    bad scores: min 2 median 6 p90 9 max 14
    good scores: min 0 median 1 p90 4 max 7
    agreement at threshold 8: 83.3% (10/12)
    suggested threshold: 9
    agreement at suggested: 91.7% (11/12)
    ```
  - 无 bad 样本：输出 `suggested threshold: n/a (no bad samples)`；`--apply` → USAGE_ERROR（退出码 2）；
  - `--apply`：打印 `apply: quality_threshold = <N>` → `set_quality_threshold` → `config updated: <路径>`；
  - 路径不存在 1；格式错误 2。
- tests：registry 的 quality 组补 feedback；端到端「标注文件 → 报告 → --apply 写 config → 重复 --apply 幂等 → 不 --apply 不写」；失败路径。

### 做到什么程度

- 作者一份带标注的试读反馈，一条命令对齐质量门。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 批注入库、多读者聚合、自动应用（仍须作者显式 --apply）。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- 修复 S2 独立审查 P2（允许触碰 core/feedback.py 与 tests/test_feedback.py）：建议阈值候选集改为分数跨度内的整数网格，杜绝 `int(best)` 截断小数候选导致「报告一致率与实际阈值不一致」；补小数分数用例（monkeypatch check_quality 返回 9.5 / 9.2 等）锁定行为。
- tests/test_cli_registry.py：quality 组 SUBCOMMANDS 补 `feedback`。
- usage.md「质量门」节补试读反馈回流（N23）：JSONL 格式、输出字段、建议阈值口径、--apply 语义、只读红线、mock 实跑示例。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260822-M5N23S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 1100+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 批注库 / 多读者聚合、自动阈值应用、与 N22 好句反馈联动。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权低价窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-22）：实施文档就绪，用户授权低价窗口内自主推进，拆包 S1。
