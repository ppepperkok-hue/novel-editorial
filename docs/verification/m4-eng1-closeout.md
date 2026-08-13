# M4-ENG-1 收尾记录（瓶颈 1：CLI 拆包）

状态：**完成**。CLI 单文件瓶颈已解决，审查链全部闭合。

## 背景

m3-closeout.md 记录瓶颈 1：`src/novel_editorial/cli/app.py` 846 行、12 个命令组，后续扩展维护成本上升，建议按命令组拆模块。

## 实施

- `918bf7d`：app.py 拆为入口 + 11 个命令组模块（works / agents / talk / style / memory / draft / review / decision / quality / plot / events），新增命令清单测试 test_cli_registry.py。
- `121b52c`：清除 talk/draft 延迟 import 的隐藏循环依赖，改为模块顶部直连 `build_client`；修正 extension.md 文档指针。
- `73b7ea5`：补齐 5 个混合 talk/draft 用例的 `cli.talk.build_client` patch。
- `6d02f2e`：inspect 用例 talk mock 回复与 draft 解耦，恢复版本层断言强度。

## 验证

- 全量测试：237 passed。
- ruff check：All checks passed。
- pyright：0 errors, 0 warnings, 0 informations。
- 宪法校验：OK。
- 真实场景冒烟：scripts/smoke_m3.py SMOKE OK（M3 闭环每一步 exit 0）。
- 压力基线：沿用 m3-closeout.md 归档数据（拆包为纯结构重构，无性能路径变更）。

## 审查链

- 918bf7d 初审：2 条（P2 隐藏循环依赖 / P3 extension.md 指针）→ 121b52c 修复。
- 121b52c 终审：1 条 P2（混合用例 talk 侧 patch 缺失）→ 73b7ea5 修复。
- 73b7ea5 终审：1 条 P3（talk 回复复用削弱版本层断言）→ 6d02f2e 修复。
- 6d02f2e 复审查：Ready to merge。
- 报告归档：docs/reviews/20260814-M4-ENG1-initial.md、docs/reviews/20260814-M4-ENG1-fix.md。

## 结论

瓶颈 1 收口，CLI 按命令组拆分完成，后续增量开发在 `cli/` 模块内扩展即可。下一瓶颈：检索性能（inspect/memory search 全表扫描基线 ~1.4s，50 万字量级），方案确认后派包。
