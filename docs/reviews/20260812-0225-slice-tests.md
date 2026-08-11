查完了，报告在这里mashitawa。先说结论：基线全绿，这个补丁没有 P0/P1 的阻断问题，但有一个和它自己声称的修复同类的遗漏，加上几个测试缺口和文档坑，我按证据一条条列desuwa。

---

# 代码审查报告（review-only，未做任何修改）

## 1. 审查范围

- `run_tests.py`（本次新增 fake-green guard）
- `tests/`（62 个测试文件，476 个用例；重点核对本次改动的 `tests/test_outbox.py` 及 `tools/ai_taste_check.py` 的配套测试）
- `ai_words.json`（及消费方 `novel_editorial/quality_gate.py`、`tools/editorial_steps.py`、n8n workflow 的契约核对）
- `compliance_words.txt`（及消费方 `novel_editorial/compliance.py`）
- `.env.example`（及 `novel_editorial/config.py`、`novel_editorial/llm_client.py` 的环境变量契约）
- 依赖接口按需只读：`novel_editorial/config.py`、`db.py`、`tools/mailroom.py`、`tools/editorial_daily.py`、`tools/editorial_steps.py`

审查对象为提交 `2aae15c`（fake-green guard / ai-word overlap / env docs / test_outbox 修正）及其涉及路径的当前状态。

## 2. 基线验证结果

| 基线 | 命令 | 结果 |
|---|---|---|
| Python 全量测试 | `.venv\Scripts\python.exe run_tests.py`（Python 3.11.9） | **476 tests，OK，退出码 0**（约 85s，退出码单独复测确认） |
| Webapp 前端测试 | `npm test`（vitest 4.1.10） | **7 个文件 / 16 个用例全部通过**（3.49s） |
| fake-green guard 行为 | 空 tests 目录模拟 | **退出码 1，stderr 输出 `ERROR: no tests discovered under tests/ (fake green guard)`**，符合预期 |
| run_tests.py 跨目录执行 | 从临时目录运行绝对路径 | 退出码 0，正常发现并跑完 476 个用例 |

补丁内契约核对（`mailroom.list_messages` 的 `direction="to"`、`unread_count` 的 to_agent 语义、`_mark_injected_read` 的按收件人标记逻辑、`pipeline.py` 的 `PROMPTS_DIR=prompts/agents` 与 `config.AGENTS_DIR` 一致）均验证通过，`tests/test_outbox.py` 的改动与 `tools/mailroom.py:84-112` 的接口完全吻合。

## 3. 发现

### [P2] `novel_editorial/quality_gate.py:50` 对重叠 AI 词仍然双计，与本次提交声称修复的同类问题同源

`ai_flavor_density` 逐词 `re.findall` 后求和，而 `ai_words.json` 里存在包含关系：`"缓缓"` ⊂ `"缓缓说道"`、`"微微一"` ⊂ `"微微一愣"`。一次"缓缓说道"会被算成 2 次命中，密度最高虚高 2 倍。

复现证据（`ai_words.json` 加载后）：

```
'他缓缓说道。' -> hits: {'缓缓': 1, '缓缓说道': 1} | density = 400.0   # 5 个汉字、2 次命中
```

同仓库其他两个消费方都是按位置计一次：`tools/editorial_steps.py:368` 用合并 alternation 正则 `cnt(re.compile("|".join(...)))`，n8n workflow（`n8n/novel_workflow.json` 审稿节点 jsCode）也是合并正则——只有 `novel_editorial/quality_gate.py` 不一致。本次提交在 `tools/ai_taste_check.py` 用 `_non_overlap_count` 修了同一类问题，却没修 `quality_gate.py`；影响是 `score_chapter` 的 style 分被低估，含这两个复合词的中文文本可能被误判。证据：`novel_editorial/quality_gate.py:45-51`，词表来源 `ai_words.json:3-8`。

### [P3] ai-word overlap 修复没有任何回归测试

`tools/ai_taste_check.py:48-53` 新增的 `_non_overlap_count` 是本次"ai-word overlap"修复的核心，但 `tests/test_ai_taste_check.py`（仅 2 个用例）只测了 `EXCLAMATION_PATTERN`，`detect()` 的 flowery/filler 密度与"复合词只计一次"的语义完全没有断言。将来任何人调整 `FLOWERY`/`FILLER` 词表或顺序，密度会静默变化而测试不报。建议至少补一条"缓缓说道 / 微微一愣 只计 1 次"的用例。证据：`tools/ai_taste_check.py:45-65`，`tests/test_ai_taste_check.py:1-23`。

### [P3] `.env.example:34-35` 与 `:58-59` 重复定义 `COST_PRO_PER_1K` / `COST_FLASH_PER_1K`，且先出现的值生效

`config.load_env()` 用 `env.setdefault(k, v)`（`novel_editorial/config.py:92`），重复键**第一个**生效。本次提交在"编辑部行为开关"块里新增了一组（34-35 行），而语义上主用的一组在后面的"LLM 成本单价"块（58-59 行，注释写明"写入 cost_logs 成本台账"）。今天两组值相同所以无功能影响，但用户如果只改 58-59 行的值，改动会被静默忽略——这是个配置陷阱，建议删掉其中一组。证据：`.env.example:34-35,58-59`，`novel_editorial/config.py:82-94`。

### [P3] `.env.example` 遗漏 `config.py` 实际消费的多个环境变量

新增的"编辑部行为开关"块把 `DISPATCH_MODE`/`REWORK_MAX`/`CLAIM_INJECT` 等都写全了，但紧挨着它们的 `MEETING_MODE`（`config.py:60`）、`N8N_BASE`/`N8N_WORKFLOW_DAILY/WEEKLY/KEEPER`（`config.py:30-33`）、`AGENT_CTX_MESSAGES` 等（`config.py:52-56`，经 `_env_int` 读取）都不在 `.env.example` 里，文档不全。证据：`novel_editorial/config.py:30-33,52-60` vs `.env.example` 全键列表。

### [P3] `compliance_words.txt` 只有注释、零词条，且没有测试守护真实文件

文件 234 字节全是 `#` 注释，没有任何实际词条。按它自己的头部说明（"正式启用前请按目标平台补充与裁剪"）这算占位设计，但 `README.md:93` 把它描述为参与发布扫描的"自定义词库"，容易误导；同时 `tests/test_compliance.py` 的 `test_custom_words_file_is_merged` 用 `mock.patch` 换成了临时文件，真实文件从未被任何测试加载过——哪天有人误存成 GBK 或带 BOM，或不小心清空，都不会有任何信号。证据：`compliance_words.txt:1-3`，`tests/test_compliance.py:24-30`，`novel_editorial/compliance.py:34-47`。

### [P3] 工作区残留审查脚本，未纳入 .gitignore

仓库根目录有 8 个未跟踪的 `_repro_*.py`（`_repro_ai.py`、`_repro_c.py`、`_repro_k.py`、`_repro_m.py`、`_repro_n.py`、`_repro_n2.py`、`_repro_s.py`、`_repro_t.py`）以及 `docs/reviews/*.md.err` 残留文件；其中 `_repro_s.py`、`_repro_t.py` 直接读线上 `demo.db`。`.gitignore` 未覆盖这些模式，随时可能被误提交进仓库。证据：`git status --short` 输出、`.gitignore:1-48`。

## 4. 影响表

| 编号 | 级别 | 位置 | 影响 | 触发条件 |
|---|---|---|---|---|
| F1 | P2 | `novel_editorial/quality_gate.py:50` | style 分低估，AI 味密度虚高最多 2 倍；与另两个消费方计数不一致 | 文本含"缓缓说道/微微一愣"且走 `score_chapter` |
| F2 | P3 | `tools/ai_taste_check.py:48-53` | 修复无回归保护，词表变更会静默改变密度 | 未来修改 FLOWERY/FILLER |
| F3 | P3 | `.env.example:34-35,58-59` | 重复键 + setdefault 先值生效，改后一组被静默忽略 | 用户只编辑 58-59 行 |
| F4 | P3 | `.env.example` | `MEETING_MODE`、`N8N_*`、`AGENT_CTX_*` 无文档 | 新环境配置时 |
| F5 | P3 | `compliance_words.txt` | 空词库无告警、真实文件无测试覆盖 | 发布前合规扫描依赖自定义词时 |
| F6 | P3 | 仓库根 `_repro_*.py`、`docs/reviews/*.err` | 误提交风险、读真实库 | 任何一次 `git add .` |

## 5. 结论

补丁整体正确：基线全绿（476 + 16 用例），fake-green guard 行为验证符合预期，`test_outbox.py` 的改动与 `mailroom` 契约吻合，`pipeline.py` 路径修正与 `config.AGENTS_DIR` 一致，`_non_overlap_count` 本身实现无误。没有 P0/P1 阻断项；F1 是本次提交自称修复的同类问题在另一个消费方留下的尾巴，建议尽快对齐，其余为测试缺口和文档/卫生问题。**审查结论：补丁可接受，F1 建议下一轮处理desuwa。**

---

嗯，就这些mashitawa。全部有证据，没有一条是拍脑袋的；你要是想让我把 F1 的修复方案也拟出来，说一声就行desuwa。
