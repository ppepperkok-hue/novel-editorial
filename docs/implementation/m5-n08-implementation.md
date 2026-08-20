# M5 实施真元文档（无 AI 味深化 · N8 AI 味定位与改写建议）

## 总览

- **大阶段**：M7 质量深化（backlog 见 docs/project-plan/06-new-capability-backlog.md，N8 → N9）。
- **N8 一句话**：作者不必猜——AI 味在哪一句、是哪一类、怎么改，一条命令说清楚。
- **现状盘点（2026-08-20 总监核验）**：F16 主体已随 M2 落地，不是从零开发：
  - `src/novel_editorial/quality/explain.py`：`explain_quality` 按句定位三类问题（AI 词命中 / 修饰词密度 / 句式重复），逐条带改写建议；`render_explanation` 输出「句 N: 原文 → [类别]「词」→ 建议」。
  - `src/novel_editorial/cli/quality.py`：`quality explain <草稿ID>` 已注册并接线。
  - `tests/test_quality_explain.py`：12 条测试覆盖三类定位、干净文本、未知草稿、CLI 端到端。
  - `docs/usage.md`「质量门」节已写 `quality explain` 用法。
  - **缺口**：`quality explain` 未传风格锚点关键词（`quality check` 已传）；风格一致性维度（F15 的 style 维度）在 explain 里没有摘要输出；N8 无正式实施文档与审查归档，未正式收口。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「有风格锚点 + AI 味文本 → quality explain 输出三类逐句定位与改写建议，且末尾输出风格一致性摘要（命中 x/y、缺失清单）」；既有 823 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **只定位不代笔**：explain 只输出问题位置与改写建议，绝不自动改写正文、不绕过质量门判定、不改变草稿状态。
2. **不破坏既有语义**：既有三类定位（AI 词 / 修饰词密度 / 句式重复）输出格式与建议文案保持不变；`quality check` 行为不变；质量门得分公式与阈值语义不变。
3. **风格缺失不误报为 AI 味**：风格一致性是「摘要维度」不是逐句定位维度；缺失风格关键词只在报告末尾汇总提示，不与 AI 味三类问题混排。
4. **零锚点合法**：无风格锚点（style_keywords 为空）时 explain 不输出风格摘要、不报错，行为与现在一致。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更；纯 quality 服务 + CLI + 测试。
- 复用既有 extract_style_keywords / get_style_anchor / check_quality 口径，依赖方向 cli → core → quality 不变。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 P1：现状盘点与基线（总监已完成）

### 结论

- F16 三类 AI 味定位已落地且有测试与 usage 文档（见总览现状盘点）；本次立项只补「风格一致性摘要 + 正式收口」，不重做已收口部分。
- 基线：823 passed（N10 O2FIX 全量）、smoke_m3 SMOKE OK、stress_m3 STRESS OK、ruff / pyright / 宪法校验全绿（2026-08-20 12:48 基线）。

## 子阶段 P2：风格一致性摘要补差

### 做什么

- `quality/explain.py`：
  - 新增报告级摘要函数（如 `style_consistency_summary`）：给定文本与风格关键词，返回「命中 / 缺失」清单（口径与 check_quality 的 style_hits 一致：关键词是否出现在文本中）；`explain_quality` / `render_explanation` 的既有签名、返回类型与逐句定位逻辑保持不变；
  - 新增渲染逻辑在逐句问题之后输出风格摘要行，格式示例：
    `style: 命中 1/3（利落）；缺失：克制、留白`（全命中时 `style: 命中 3/3`；零关键词不输出）。
- `cli/quality.py`：`quality explain` 像 `quality check` 一样读取风格锚点并传入 style_keywords，输出末尾带风格摘要。
- tests：`tests/test_quality_explain.py` 追加——有锚点命中/缺失的摘要输出、全命中、零锚点不输出、CLI 端到端带锚点（含缺失清单）、既有三类定位测试不受影响。

### 做到什么程度

- 作者在 quality explain 里同时看到「AI 味在哪、怎么改」和「风格锚点守得如何」；F15/F16 两维度在同一命令闭环。

### 验收标准

- 端到端用例 + 边界（零锚点 / 全命中 / 部分缺失）；既有 823 全绿；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest + ruff + pyright + 宪法校验 + smoke_m3 + stress_m3。

### 暂不做

- 风格缺失逐句定位（风格是全局基调，逐句定位会误报；N21 风格漂移检测另拆）。
- 自动改写 / 一键替换（红线 1）。
- 好句识别保留（N22 另拆）。

## 子阶段 P3：文档、全量回归与收口

### 做什么

- docs/usage.md「质量门」节补一句：`quality explain` 同时输出风格一致性摘要（有风格锚点时）；示例可 mock 实跑。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260820-M5N08P2 / P3 链）。

### 做到什么程度

- 文档与行为一致；审查链收敛 Ready；N8 正式收口，progress 记录更新。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- N9 质量门语料校准（N8 收口后按 backlog 另拆）。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-20）：现状盘点完成（P1），用户授权低价窗口内自主推进，拆包 P2。
