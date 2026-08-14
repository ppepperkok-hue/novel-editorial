# M4-ENG-3 实施真元文档（瓶颈 3：测试分片 / 本地子集）

## 总览

- **大阶段**：M4 工程瓶颈优化。瓶颈 3 = 全量 pytest 顺序执行约 69s（259 个测试 / 25 个文件）；本地想快速跑子集、CI 想并行分片都没有抓手。
- **现状（实测）**：最慢单测 0.89s，无超长用例；时长主要来自顺序执行与 CLI/DB 初始化；CI（.github/workflows/ci.yml）单 job 顺序跑 `uv run pytest -q`。
- **验收总门**：验证四连全绿；smoke 子集真实耗时达标；CI 全量真实耗时达标；无越界实现；完成即停，回报三问。

## 方案评估

### 方案 A（推荐）：pytest-xdist 并行 + smoke 子集 + 失败重跑

- 新增 dev 依赖 `pytest-xdist`。
- 本地/CI 并行：`uv run pytest -q -n auto`（按 CPU 核数自动开 worker，负载均衡分发）。
- 本地快子集：定义 `smoke` marker，挑选核心闭环代表用例（init / works / talk / draft / decision / inspect / events / demo / 质量门 / 隔离），`uv run pytest -m smoke` 目标 <15s。
- 失败重跑：`uv run pytest --lf`（pytest 内置，仅跑上次失败）。
- CI：verify job 的测试步骤改为 `-n auto`，目标总时长从 ~70s 降到 <30s。
- 优点：并行收益最大；xdist 成熟稳定；子集/重跑零成本。
- 代价：新增一个 dev 依赖（不影响运行时）。
- 风险：分片后测试间隔离依赖现有 tmp_path 与独立数据目录约定（已由 isolation 测试守卫）；xdist 与 typer CliRunner 单线程环境兼容性需实测（本项目 CLI 测试均为子进程/内存隔离，预期无冲突）。

### 方案 B（轻量，无新依赖）：原生子集 + 脚本分片

- smoke marker（pytest 内置，无需依赖）+ `-k` 关键词过滤 + `--lf` 失败重跑，满足本地子集。
- CI 分片：用 `pytest --collect-only` 取文件清单后按 shard 轮转切分（shell 脚本）。
- 优点：零依赖。
- 代价：CI 无并行（总时长不变）；collect-only 输出解析脆弱；负载不均（文件间测试数差异大）。
- 定位：若用户不接受新增 dev 依赖，则采用本方案，CI 只做文件级分片文档化。

## 子阶段划分

### A. 并行与子集落地（方案 A）

- 做什么：
  1. pyproject dev 依赖加 pytest-xdist；
  2. pyproject pytest 配置注册 `smoke` marker（不自动启用，避免 CI 行为变化）；
  3. 给核心闭环代表用例打 `@pytest.mark.smoke`（约 20-30 个，覆盖各模块关键路径）；
  4. 文档化本地命令：全量 `uv run pytest -q`、并行 `uv run pytest -q -n auto`、子集 `uv run pytest -q -m smoke`、重跑 `uv run pytest -q --lf`（README / rules.md 已同步）；
  5. CI 测试步骤改 `uv run pytest -q -n auto`。
- 做到什么程度：smoke 子集 <15s；CI 全量 <30s；全量 259 仍全绿；分片无 flake（连续跑 3 次 -n auto 全绿）。
- 涉及功能：工程瓶颈；单元 M4-ENG-3-A。
- 验收标准：上述四条真实耗时 + 3 次并行全绿。
- 验证方式：pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3（后两者确认未受影响）。
- 暂不做：矩阵分片（多 job 文件轮转）、覆盖率合并、pytest-split、测试缓存分层。
- 影响评估（涉及基底）：新增 dev 依赖 + CI 步骤调整；运行时与数据目录不变。
- 状态：已批准（2026-08-14 用户选择方案 A），待派包。

### B. 无依赖方案（方案 B，仅当用户否决 xdist 时启用）

- 只做 smoke marker + 文档化 -k/--lf；CI 保持顺序执行或按文件轮转分片脚本。
- 状态：备选，用户已选择方案 A，不实施。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 涉及基底（技术栈 / 目录 / 表设计 / 事件契约 / 错误码 / 依赖方向）的改动：先停下评估影响，给方案再实现。
- 每个子阶段完成即停，回报三问，经确认后再进下一子阶段。
