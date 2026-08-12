# Phase 0 报告（2026-08-13）

状态：**产出齐备、验证全绿；两处实账待补（git 未初始化、Alembic baseline 未落地）**。

## 一、完成项

Phase 0 四步全部完成，产出归档如下：

### 1. 立项规划

- `docs/project-plan/01-core-value.md`：核心价值（分层编辑部、创作与协作本身、去 AI 味、伙伴完整）。
- `docs/project-plan/02-editorial-operation-model.md`：运作模型（组织分层、判断分层、信息分层）。
- `docs/project-plan/03-core-goals.md`：核心目标 G1–G5（分层运作且自然、无 AI 味、伙伴完整、信息分层记忆、开源可用）。
- `docs/project-plan/04-feature-breakdown.md`：功能 F1–F21（组织 / 协作 / 信息 / 质量 / 可见性 / 开源）。
- `docs/project-plan/05-executable-units.md`：里程碑 M1–M3 与 27 个可执行单元，含自然行为限度递进。
- `docs/project-checklist.md`：立项汇总（约束、风险、决策记录）。
- 旧稿三份归档于 `docs/project-plan/archive/`，不参与现行决策。

### 2. 技术栈

- `docs/tech-stack.md`：八层决策（前端 / UI 组件库后置；Python 3.11+；Typer + FastAPI 预留 + Pydantic v2 + asyncio；SQLite + SQLAlchemy 2.0 + Alembic；REST + OpenAPI + SSE；pytest + ruff + pyright + uv；本地部署 + 环境变量密钥）。

### 3. 项目架构

- `docs/architecture/scope.md`：最小范围（只支撑 M1）与本期不做清单。
- `docs/architecture/rules.md`：通用技术规则（目录、依赖方向、错误、配置、契约、测试、提交）。
- `docs/architecture/skeleton.md`：最小骨架说明。
- `docs/architecture/extension.md`：功能接入流程与模板（`works show` 实测）。
- 骨架真实可跑：`src/novel_editorial/`（CLI / core / store / llm / quality）+ `tests/`。

### 4. Agent 宪法

- `AGENTS.md`：项目级宪法（10 条行为规则 + 加载清单 + 技术约定）。
- `scripts/verify_constitution.py`：宪法校验脚本。

## 二、验证结果（2026-08-13 复测）

| 检查 | 结果 |
| --- | --- |
| `uv run pytest` | 8 passed |
| `uv run ruff check .` | 0 错误 |
| `uv run pyright` | 0 错误 |
| `python scripts/verify_constitution.py` | OK |
| CLI 冒烟（version / health / works create / list / show） | 全部跑通，中文正常 |
| 文档 Markdown 链接扫描 | 无断链 |
| 最小链路（命令 → 业务 → 存储 → 响应） | 真实跑通（作品 + 默认四人班子落库） |

## 三、发现的偏差与问题（如实）

1. **git 未初始化**：新目录尚无 `.git`，全部文档与代码目前无版本控制。Phase 1 开工前应 `git init` 并完成首次提交，否则“归档在案”没有版本保障。
2. **Alembic baseline 未落地**：`tech-stack.md` 与 `scope.md` 声称使用 Alembic 迁移，但 `alembic.ini` 与 `migrations/` 尚未初始化（仅依赖已装）。需补 baseline，或修正文档表述。
3. **skeleton.md 测试数过时**：文档写“7 passed”，实测为 8 passed（`works show` 示例功能加入后未同步）。
4. **GitHub Actions CI 未接入**：`tech-stack.md` 计划“M1 起步即接入”，尚未建（Phase 1 待办）。
5. **占位实现（按计划，非缺陷）**：LLM 客户端仅有 Mock 实现（真实客户端属 U5）；质量门 `basic_gate` 恒通过（检测属 U13）。M1 未开始前这是预期状态。
6. **备份文件在仓库根**：`novel-editorial-backup-20260813.zip`（约 810MB）按用户要求留在目录，但未被 `.gitignore` 忽略；git 初始化后会进入版本库，建议加入忽略清单（文件本身保留）。

## 四、风险与遗留

- M1 单元 U1–U15 尚未开始实现（`works create/list/show` 为骨架级基础，非完整验收）。
- 自然行为限度：M1 只埋种子（自主发起、退稿、反驳），放宽路径已定义在 `05-executable-units.md`。
- 面板、自动发布、多作者共编等边界明确不做；FastAPI / SSE 在面板阶段启用。
- 技术风险前置项（U5 LLM 客户端、U13 质量门）已排入 M1，未提前消解。

## 五、结论

Phase 0 四步产出齐备，骨架可运行，验证全绿；但按“文档如实”原则，git 初始化与 Alembic baseline 两处账目与文档不一致，建议在 Phase 1 开工前的首个提交中一并补齐，并将本报告作为项目存档。

## 六、后续补齐记录（2026-08-13）

按用户要求补齐工程账目：

- **git 已初始化**：仓库建立（默认分支 main），完成首次提交；提交身份使用 GitHub 账号 ppepperkok-hue 与 noreply 邮箱（不暴露隐私）。
- **Alembic baseline 已落地**：`alembic.ini` + `migrations/`（baseline 迁移 `3b05b83f8953`），Schema 单一权威来源；`init` 与作品创建均走 `alembic upgrade head`，不再使用 `create_all`。
- **GitHub Actions CI 已接入**：`.github/workflows/ci.yml`，与本地同一套验证命令（pytest / ruff / pyright / 宪法校验）。
- **`.gitignore` 已补备份忽略**：`novel-editorial-backup-*.zip` 不进版本库。
- **skeleton.md 已同步**：测试数更新为 10 passed，并补充 Alembic 说明。
- **CLI 错误处理补齐**：业务错误（NovelError）输出友好信息并返回退出码 1，意外错误返回 3；`--version` 选项修复；测试增至 10 个。
