# M4-ENG-3 收尾记录（瓶颈 3：测试分片 / 本地子集）

状态：**完成**。全量 pytest 并行化 + smoke 子集 + 失败重跑落地，审查闭合。

## 背景

m3-closeout.md 记录瓶颈 3：全量 pytest 60.4s（覆盖率模式 68s），CI 可分片、本地可子集。

## 实施

- `6962195`：pyproject dev 组加 pytest-xdist；注册 smoke marker；30 个核心闭环代表用例打标；CI Run tests 改 `-n auto`；uv.lock 仅增 execnet/pytest-xdist。
- `ed6e9e5`：README 与 rules.md 文档同步并行 / 子集 / 重跑命令。

## 验证与基线

- 单进程全量：259 passed（~65-67s）。
- 并行全量（-n auto，连续 3 次）：259 passed，14.06-15.03s，无 flake。
- smoke 子集（-m smoke）：30 passed，~12-13s（目标 <15s）。
- --lf：制造失败后只重跑失败用例（验证后清理）。
- ruff / pyright / 宪法 / smoke_m3 / stress_m3：全绿。
- 本地命令速查：
  - `uv run pytest -q -n auto`：全量并行（与 CI 同一套）
  - `uv run pytest -q -m smoke`：快速核心闭环子集
  - `uv run pytest -q --lf`：只重跑上次失败

## 审查链

- 初始审查（6962195）：1 条 P3（文档同步），修复提交 ed6e9e5 闭合；报告归档 docs/reviews/20260814-M4-ENG3-initial.md。

## 结论

瓶颈 3 收口。CI 全量从 ~70s 降到 ~15s，本地迭代可用 smoke 子集与失败重跑。三个工程瓶颈（CLI 拆包 / 检索性能 / 测试分片）全部完成。
