# 2026-08-14 M4-ENG-3（瓶颈 3：测试分片 / 本地子集）初始审查报告

- 审查方式：codex exec review（独立 CLI，只读）
- 审查范围：commit 6962195（pytest-xdist 并行 + smoke 子集 + CI 加速）
- 审查依据：AGENTS.md / rules.md / docs/implementation/m4-eng3-implementation.md

### 优点

- pytest-xdist 仅加入 dev 组，uv.lock 只新增 execnet 与 pytest-xdist，运行时依赖零变化。
- 30 个 smoke 代表用例覆盖各模块关键路径（init / works / agents / talk / style / memory / draft / review / decision / quality / plot / events / inspect / log / demo / version / 隔离 / 质量门失败）。
- CI 改 `-n auto`；实测并行全量 259 passed（~14s），smoke 子集 30 passed（~12-13s），单进程全量仍绿，无 flake。
- 测试隔离经 xdist 验证无冲突（各用例 tmp_path + NOVEL_DATA_DIR 独立）。

### 问题

#### Critical（必须修）

无。

#### Important（应该修）

无。

#### Minor（可后补）

1. **P3：文档未同步并行/子集/重跑命令**
   - 文件：README.md（开发与验证命令）、docs/architecture/rules.md（验证命令）
   - 问题：CI 已改 `-n auto`，文档仍只写串行 `uv run pytest -q`，违反"本地与 CI 同一套"与实施文档步骤 4（文档化 -n auto / -m smoke / --lf）。
   - 影响：贡献者按文档跑串行，无法发现并行与子集能力。
   - 修法：README 与 rules.md 补充并行、smoke 子集、--lf 命令。

### 建议

无。

### 结论

Ready to merge: No（With fixes）

### 处理记录

- 2026-08-14 修复提交 ed6e9e5（README / rules.md 文档同步），终审 Ready to merge；验证与基线见 docs/verification/m4-eng3-closeout.md。
