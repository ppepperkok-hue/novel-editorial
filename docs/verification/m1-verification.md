# M1 验证报告（Phase 2，2026-08-13）

状态：**验证通过（待用户确认）**。M1 十五个单元全部落地，六子阶段全部通过独立审查，全量验证全绿。

## 一、全量自动化

| 检查 | 结果 |
| --- | --- |
| `uv run pytest` | 54 passed |
| `uv run ruff check .` | 0 错误 |
| `uv run pyright` | 0 错误 |
| `python scripts/verify_constitution.py` | OK |
| `uv run pytest --cov=novel_editorial` | 总覆盖率 94%；核心服务层（core/）全部 ≥ 80%（87%–100%） |
| CLI 冒烟（demo / version / health） | 全部跑通 |

## 二、真实场景验证

`scripts/smoke_m1.py`（已入库，可复现）在临时数据目录跑通完整闭环：

init（含幂等）→ works create → works show → agents show → style set → memory pack → talk send（含 @写手 中文标点）→ draft generate → quality check → review add（责编退稿）→ draft revise（写手反驳，版本 v2）→ draft list → decision accept → draft show（含 reason）→ review list → decision list → log（聚合对话/草稿/意见/决策）→ demo → works list。

全部退出码 0，输出符合预期。

## 三、边界与失败验证

| 场景 | 期望退出码 | 结果 |
| --- | --- | --- |
| workspace / draft 不存在 | 1 | 通过 |
| 未知 @别名 / reviewer 别名 | 2 | 通过 |
| 重复 accept | 2 | 通过 |
| revise / regenerate accepted 草稿 | 2 | 通过 |
| accept quality_failed 草稿 | 2 | 通过 |
| 无效质量阈值配置 | 1（配置错误） | 通过 |
| 空 LLM 内容拒绝落库 | 1 | 测试覆盖 |
| 旧库自动迁移补表 | 0 | 测试覆盖 |

错误路径均显式报错，无静默吞错。

## 四、回归

- `tests/conftest.py` 全局强制 mock LLM，测试不依赖本机 key。
- 六个子阶段各自独立审查发现的问题（alias 标点、副作用残留、退出码、布局下沉、唯一约束、空内容、阈值一致性、状态机、测试强度、mock 固定）均已修复并有回归测试。
- M1 总审修复（提交 b6c1248）：`has_proactive_message` 精确匹配 `kind=proactive_question`（反驳消息不再误吞主动提问）；demo 在质量门拦截时优雅降级（reject 并汇报），不再崩溃退出。

## 五、对照立项（G1–G5）

### G1【必须】分层编辑部真实且自然地运作

- 闭环真实跑通：老板下令 → 讨论（含责编主动提问、写手反驳，`initiator=agent` 可识别）→ 写手产出 → 质量门 → 老板拍板。
- 无强制关卡；作者随时介入（accept / reject / note）。
- 多作品数据隔离。

证据：smoke 全链路、demo、`tests/test_demo.py`、`tests/test_isolation.py`。

### G2【必须】作品无 AI 味

- 质量门可量化：AI 味词表命中 + 修饰词密度，报告含 score / details / passed。
- 测试集 20 例（明显 AI 味 / 正常各 10）判定 100% 正确（≥ 90% 达标）。
- 超阈值拦截：草稿标记 `quality_failed`，不可 accept；阈值经环境变量 / config.toml 可配。

证据：`tests/test_quality.py`。

### G3【必须】伙伴是完整的人

- 四角色默认班子有性格与立场档案，CLI 可查看。
- 写手在收到 agent 意见时自动反驳并留痕（`initiator=agent, kind=rebuttal`）。
- 完整档案、立场拒绝、私有记忆属 M2（U16–U18），M1 不要求。

证据：`tests/test_agents.py`、`tests/test_review_decision.py`。

### G4【应该】信息分层与记忆

- 写作记忆包：作品档案 + 风格锚点 + 禁忌词 + 章纲占位，跨作品不串。
- 创作日志聚合对话 / 版本 / 意见 / 决策，可逐步回溯。
- 每作品独立 SQLite 库，隔离验证通过。
- 按需检索、来源引用属 M2（U19），M1 不要求。

证据：`tests/test_draft.py`、`tests/test_isolation.py`、`tests/test_quality.py`（log 聚合）。

### G5【可以】开源可用

- M3 范围（U24–U25），M1 不要求。如实记录：README / 快速开始尚未编写。

## 六、审查闭环

- 六子阶段独立审查：A/B/C/D/E/F 各一次，全部处理并提交。
- M1 总体审查（base 7f74236..HEAD）：2 个 P2 缺陷（主动提问误抑制、demo 质量门崩溃）均已修复并补回归测试；其余检查项（依赖方向、迁移链、状态机、安全、文档一致）无阻断问题。

## 七、遗留与风险

- M2 / M3 未开始（backlog 已排）。
- 真实 LLM key 端到端未验证（当前无 key 环境，mock 全绿）；demo 已对质量门失败做降级处理。
- 质量门阈值（默认 8）与词表为初版，随真实语料迭代校准（立项约束）。

## 八、结论

M1 达成 Phase 2 验收门：全量验证全绿、G1–G4 逐条达成并有证据、边界失败有验证记录、审查意见已处理。G5 按里程碑排期到 M3。待用户确认后进入 Phase 3 交付或直接推进 M2。
