# 2026-08-14 M4-ENG-1（瓶颈 1：CLI 拆包）初始审查报告

- 审查方式：codex exec review（独立 CLI，只读）
- 审查范围：commit 918bf7d（CLI 命令组拆模块）
- 审查依据：AGENTS.md / rules.md / extension.md / docs/architecture/skeleton.md / docs/verification/m3-closeout.md 瓶颈 1

### 优点

- app.py 从 846 行拆为入口 + 11 个命令组模块，职责边界与 skeleton.md 一致；命令清单测试（test_cli_registry.py）确保拆包后全部命令仍可调用。
- 拆包后依赖方向保持 cli → core / store / llm，未引入反向依赖。

### 问题

#### Critical（必须修）

无。

#### Important（应该修）

1. **P2：talk/draft 延迟 import 造成隐藏循环依赖**
   - 文件：src/novel_editorial/cli/talk.py、src/novel_editorial/cli/draft.py
   - 问题：命令内部延迟 `from novel_editorial.cli.app import build_client`，使 cli 包内模块互相引用，形成隐藏循环依赖；同时掩盖了模块实际 import 位置，测试 patch 目标不清晰。
   - 影响：import 图不干净，后续拆包或静态分析易误判；patch 目标必须跟着旧命名空间走，脆弱。
   - 修法：改为模块顶部直接 `from novel_editorial.llm.client import build_client`，测试同步改 patch 目标。

#### Minor（可后补）

2. **P3：extension.md 指向旧 app.py**
   - 文件：docs/architecture/extension.md
   - 问题：文档仍引用 `src/novel_editorial/cli/app.py` 作为命令注册示例，与拆包后的 `cli/` 模块结构不符。
   - 影响：新功能接入者按旧路径找代码会落空。
   - 修法：更新文档指针到对应命令组模块。

### 建议

无。

### 结论

Ready to merge: No（With fixes）

### 处理记录

- 2026-08-14 派修复任务包 M4-ENG-1-FIX1；修复提交 121b52c（顶部直连 import + extension.md 指针修正），独立终审仅剩 1 条 P2（见下文 fix 报告链）。
- 121b52c 终审 P2：5 个同时调 talk 与 draft 的测试只 patch 了 `cli.draft.build_client`，talk 侧依赖 conftest 删 key 兜底（隐性依赖、潜在假绿）；由 73b7ea5 补 talk 侧 patch。
- 73b7ea5 终审 P3：talk patch 复用 draft reply，削弱 inspect 版本层断言；由 6d02f2e 改为独立回复。
- 6d02f2e 复审查 Ready to merge，详见 [20260814-M4-ENG1-fix.md](20260814-M4-ENG1-fix.md)。
