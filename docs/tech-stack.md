# 技术栈（Tech Stack）

决策依据：立项清单（[project-checklist.md](project-checklist.md)）与“项目与 AI 适配”原则。本项目为本地运行的 CLI/API 工具，面板后置；选型以成熟稳定、显式可预测、可验证、最小依赖为准。

## 第 1 层：前端技术栈

**决策：本轮不选（后置）**

- 原因：立项边界明确“图形前端面板与桌面应用后置，先行 CLI / API 交互”；M1–M3 均为 CLI / API 形态。
- 后续：进入面板阶段时走同一流程补选，并参考终极开发 skill 的 `02a-frontend.md`。

## 第 2 层：UI 组件库

**决策：本轮不选（后置）**

- 原因：同第 1 层，面板后置；CLI 使用终端文本输出，不引入 UI 组件库。

## 第 3 层：后端语言与运行时

**决策：Python 3.11+（requires-python >= 3.11, < 3.13）**

- 候选：Python / TypeScript(Node) / Go / Rust。
- 理由：多 Agent 与 LLM 生态最成熟（客户端、提示工程、异步）；前身同为 Python，参考代码可复用；AI 语料覆盖广，参与开发维护的 Codex 产出质量高。
- 否决项：Node/TS——面板后置，CLI 核心用 Python 生态更顺，暂不需要前后端同构；Go/Rust——LLM/Agent 生态相对薄，学习与维护成本高，无性能刚需。

## 第 4 层：开发框架

**决策：Typer（CLI）+ FastAPI（API，面板阶段启用）+ Pydantic v2 + asyncio**

- 候选：Typer/Click、FastAPI/Django、SQLModel。
- 理由：Typer 基于类型注解生成 CLI，显式可预测，适合 AI 开发；FastAPI 自动生成 OpenAPI、与 Pydantic 一体，为面板与可见性（SSE）预留；asyncio 支撑 LLM 并发与流式事件。
- 否决项：Django——重，模板与 ORM 绑定过多，不符合最小依赖；Click 裸用——类型友好度低于 Typer。
- 约束：业务逻辑放独立服务层，CLI 与 API 共享同一套业务层，不各写一遍。

## 第 5 层：数据与存储

**决策：SQLite（WAL）+ SQLAlchemy 2.0 + Alembic；本地文件系统存草稿与导出**

- 候选：PostgreSQL / MySQL / SQLite；SQLAlchemy / SQLModel / 裸 sqlite3。
- 理由：本地单用户、零运维、文件即备份；多作品隔离天然实现为“每部作品一个 SQLite 文件 + 全局库（作品注册与用户配置）”；SQLAlchemy 2.0 类型化、schema 显式可见、AI 面 schema 写查询可靠；Alembic 管理迁移。
- 否决项：PostgreSQL——单用户本地过重；MongoDB——数据强一致、关系型更贴合；自研存储层——调试成本高、易出错。
- 缓存：不需要 Redis（本地单用户，无并发规模需求）。

## 第 6 层：API 与通信契约

**决策：CLI 命令即首要契约；API 采用 REST + OpenAPI（/v1），实时事件用 SSE；统一 Pydantic 模型**

- 理由：M1–M3 以 CLI 交互为准，命令名即契约；面板阶段 FastAPI 自动生成 OpenAPI，前后端按同一契约并行开发；可见性三扇窗中的实时观察流用 SSE（单向事件流够用，比 WebSocket 简单）。
- 事件契约先行：定义统一事件类型（如 `agent.message`、`draft.created`、`quality_gate.passed`、`decision.requested`、`review.rejected`），创作日志与可见性共用同一事件结构。
- 版本化：API 前缀 `/v1`；契约变更走版本化策略，不静默破坏。

## 第 7 层：测试与质量工具链

**决策：pytest + pytest-asyncio + ruff + pyright + uv（uv.lock）**

- 理由：pytest 为 Python 主流测试框架，与 asyncio 配合测异步逻辑；ruff 同时覆盖 lint 与 format；pyright 类型检查对 AI 开发友好；uv 为包管理与环境工具（AGENTS.md 指定 Python 优先 uv）。
- 验证链路：`uv run pytest`、`uv run ruff check`、`uv run pyright`，本地与 CI 同一套命令。
- CI：GitHub Actions 已接入（`.github/workflows/ci.yml`，与本地同一套命令）；端到端演示命令（U15）将作为 CI 中的集成验收。

## 第 8 层：部署、可观测性与安全

**决策：本地运行；结构化日志 + 健康检查 + 关键节点提醒；密钥走环境变量，绝不入库**

- 部署形态：本地 CLI 工具，无服务器/容器；面板阶段为本机 FastAPI + uvicorn。
- 可观测性：系统日志（运行与错误）与创作日志（业务）分离；API 阶段提供 `/healthz`；关键节点失败通过 CLI 提醒（F19 基础形态）。
- 密钥管理：LLM API key 从环境变量或本地配置文件读取，提供 `.env.example` 模板；密钥与 lock file 永不进仓库。
- 备份与恢复：SQLite 文件即备份，迁移用 Alembic；归档策略沿用项目 `backups/` 概念。
- 安全：本地单用户，无复杂 Auth；若未来 API 对外暴露，再补 token 认证（记录在案，不在本轮实现）。

## 验收门

- 八层逐层有决策，跳过层（前端、UI 组件库）已记录原因。
- 每层选型已过“项目与 AI 适配”检查：成熟稳定、显式可预测、可验证、版本可锁定。
- 版本锁定：uv.lock 锁定依赖；运行时限定 Python 3.11–3.12。
- 用户逐层确认无异议。

通过后进入项目架构（终极开发 skill 的 `03-architecture.md`）。
