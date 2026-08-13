# M3 验证报告（Phase 2，2026-08-14）

状态：**验证通过（待用户确认）**。M3 的 U24/U25 文档与 U26 可见性三形态全部落地，M3-A / M3-B1 / M3-B2 / M3-B3 独立审查全部闭合；全量验证覆盖整个项目（M1–M3 回归），全绿。

## 一、全量自动化

| 检查 | 结果 |
| --- | --- |
| `uv run pytest` | 196 passed |
| `uv run ruff check .` | 0 错误 |
| `uv run pyright` | 0 错误 |
| `python scripts/verify_constitution.py` | OK |
| `uv run pytest --cov=novel_editorial` | 总覆盖率 97%；核心服务层（core/）全部 ≥ 80%（87%–100%） |
| CLI 冒烟（demo / version / health） | 全部跑通 |

## 二、真实场景验证

`scripts/smoke_m3.py`（已入库，可复现）在临时数据目录跑通完整闭环，16 步全部 [OK]、退出码 0、输出 SMOKE OK：

init（含幂等）→ works create → style set → talk send → talk @写手 路由 → memory pack → draft generate（质量门通过，输出 awaiting decision）→ events list（含 quality_gate.passed / decision.requested）→ inspect（命中档案与对话两层且带来源）→ review add 责编退稿 → draft revise（仍输出 awaiting decision，v2）→ decision pending 列出草稿 → decision accept → decision pending 空态 → demo。

脚本强制剔除 `NOVEL_LLM_*` 环境变量走确定性 mock，本地配不配 key 结果一致，冒烟可复现。

## 三、边界与失败验证

| 场景 | 期望退出码 | 结果 |
| --- | --- | --- |
| events list 未知事件类型 | 2 | 测试覆盖（test_events.py） |
| inspect 空关键词 | 2 | 测试覆盖（test_inspect.py） |
| inspect 无命中 | 0，输出 no matches | 测试覆盖 |
| inspect 跨作品隔离 | 0，互不命中 | 测试覆盖 |
| decision pending 空态 | 0，输出 no pending decisions | 测试覆盖 + smoke |
| quality_failed 草稿不出现在 pending、无 awaiting decision | 0 / 无提示 | 测试覆盖（test_decision_pending.py） |
| accept / reject 后从 pending 消失 | 0 | 测试覆盖（accept + reject 双路径） |
| 跨进程同时间戳事件不丢（events watch 游标） | 0 | 修复 e93acc1 + 回归测试（固定时钟复现） |
| 旧库自动迁移补 events 表 | 0 | 测试覆盖（test_memory / test_mood / test_plot 升级用例） |
| workspace / draft 不存在、重复 accept、accepted 再修订等 M1 边界 | 1 / 2 | 回归全绿 |

错误路径均显式报错，无静默吞错。

## 四、回归

- `tests/conftest.py` 全局强制 mock LLM，测试不依赖本机 key。
- M1 / M2 全部回归通过；M3 各子阶段独立审查发现的问题（PowerShell 参数拆分、示例输出前缀、.env 引号、跨进程事件丢、inspect 空格关键词与辅助字段命中、reject 端到端覆盖）均已修复并有回归测试。
- 事件游标采用 SQLite rowid（插入序单调），跨进程并发写入不丢；VACUUM 理论残余风险已评估（项目无删除 / VACUUM 路径）。

## 五、对照立项（G1–G5）

### G1【必须】分层编辑部真实且自然地运作

- 闭环真实跑通：老板下令 → 讨论（含责编主动提问、写手反驳，`initiator=agent` 可识别）→ 写手产出 → 质量门 → 老板拍板。
- 老板穿透：`inspect` 跨八层检索带来源；`events list / watch` 实时掌握动静；`decision pending` 关键节点提醒。
- 多作品数据隔离。

证据：smoke_m3 全链路、`tests/test_demo.py`、`tests/test_isolation.py`、`tests/test_events.py`、`tests/test_inspect.py`。

### G2【必须】作品无 AI 味

- 质量门量化：AI 味词命中 + 修饰词密度 + 句式重复 + 风格一致性，报告含 score / details / passed。
- 测试集（明显 AI 味 / 正常段落）判定达标（≥ 90%）。
- `quality explain` 定位句段并给改写建议；超阈值拦截（quality_failed 不可 accept）。

证据：`tests/test_quality.py`、`tests/test_quality_explain.py`。

### G3【必须】伙伴是完整的人

- 完整档案（价值观、审美、情绪基线、工作习惯、弱点、人际预设、私心）可查看、可编辑。
- 立场与拒绝：违背判断的任务直接拒绝并留痕；私有记忆互不相通；情绪随互动沉淀。

证据：`tests/test_agents.py`、`tests/test_refusal.py`、`tests/test_memory.py`、`tests/test_mood.py`。

### G4【应该】信息分层与记忆

- 分层默认视图（写手记忆包 / 编辑视图 / 老板视图）+ `memory search` 带来源检索。
- 叙事追踪：伏笔 / 目标 / 钩子埋设、回收、注入悬置线索。
- 每作品独立 SQLite 库，隔离验证通过；老板可穿透任意层。

证据：`tests/test_views.py`、`tests/test_plot.py`、`tests/test_isolation.py`。

### G5【可以】开源可用

- README 快速开始 + 配置/FAQ 文档，干净环境 30 分钟跑通；示例输出与真实 CLI 逐字一致（M3-A 审查实测）。
- `scripts/smoke_m3.py` 一条命令复现完整闭环；README 已注明仓库地址。

证据：README / docs/usage.md / docs/reviews/20260814-M3A-fix.md / smoke_m3 输出。

## 六、审查闭环

- M3-A（U24/U25）：初始 2 P2 + 1 P3，修复 4f94e51，终审 Ready to merge。
- M3-B1 事件流（62bdf7a）：P2 跨进程事件丢，修复 e93acc1（rowid 游标），终审 Ready to merge。
- M3-B2 穿透查询（0e6ed4e）：2 P3（空格关键词、辅助字段命中不可见），修复 ceae3a9，终审 Ready to merge。
- M3-B3 拍板提醒（770aa9d）：P2 reject 缺端到端覆盖，修复 4a15c63，终审 Ready to merge。
- 全部报告归档于 docs/reviews/，审查汇总索引更新至 4 P1 / 22 P2 / 16 P3。

## 七、遗留与风险

- U27 图形面板（三扇窗）按计划后置，不阻塞 CLI 里程碑。
- 真实 LLM key 端到端未验证（当前无 key 环境，mock 全绿）。
- 质量门阈值（默认 8）与词表为初版，随真实语料迭代校准（立项约束）。
- events watch 的 rowid 游标在引入事件删除或 VACUUM 后需重新评估。

## 八、结论

M3 达成 Phase 2 验收门：全量验证全绿、G1–G5 逐条达成并有证据、边界失败有验证记录、审查意见全部处理。M1–M3 CLI 里程碑线完整，剩余 U27 图形面板为计划后置项。待用户确认后进入 Phase 3 交付收尾，或直接立项 U27。
