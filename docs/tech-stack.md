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

---

# N12 图形面板技术栈补选（2026-08-22）

背景：N12 面板立项（docs/project-plan/08-n12-panel-checklist.md）进入选技术栈阶段。面板是 N24 API 的图形消费方，本地单机运行；选型遵循「项目与 AI 适配」：成熟稳定、显式可预测、可验证、最小依赖。以下为第 1/2 层补选与第 3–8 层沿用记录。

## 第 1 层：前端技术栈（补选）

**决策：React 18 + TypeScript + Vite（SPA），构建产物由 FastAPI 静态托管**

- 候选：React+TS+Vite / Vue3+TS+Vite / 原生 TS+Vite / 零构建原生 HTML/CSS/JS / HTMX+Jinja2。
- 理由：
  - 面板是长期功能（三扇窗 → SSE → 更多窗口），框架收益随交互复杂度上升；
  - TypeScript 显式类型让 AI 少猜错、长期可维护；React 生态主流、AI 训练覆盖广、官方文档全；
  - Vite 构建显式可复现，lint / 类型检查 / 测试命令清晰；
  - 构建产物（dist）由 FastAPI 静态托管，运行期不依赖 Node——Node 仅开发 / 构建期，外部使用者跑面板不需要 Node。
- 后果：仓库新增 `frontend/` 目录（package.json + lock + Vite 配置）；CI 增加前端 lint / type / test 步骤；开发机需要 Node（版本锁定记录于 frontend/）。
- 否决项：
  - Vue3——同为成熟方案，但项目无既有偏好，React 生态与示例面更大；
  - 原生 TS（无框架）——三扇窗 + 抽屉 + 轮询的状态管理会手写膨胀；
  - 零构建原生 JS——无类型、难测试、增长吃力，与「面板会长期长大」不符；
  - HTMX / Jinja2 SSR——动态仪表盘用轮询 + 抽屉交互，SPA 更贴合，且与 N24 JSON API 同源原则一致。

## 第 2 层：UI 组件库（补选）

**决策：不引入重型组件库；自建设计 token（CSS 变量）+ 原生 CSS；图标用 Phosphor（统一 strokeWidth）**

- 候选：Tailwind / Ant Design / shadcn/ui / 无组件库（设计 token + 原生 CSS）。
- 理由：面板页面少（三扇窗 + 抽屉），组件库收益低、样式覆盖成本高；手写组件可控、包体小；遵循前端设计 skill 的一致性锁（单 accent、单圆角体系、单明暗主题、单图标家族）。
- 后果：基础组件（Button / Card / Drawer / Empty / Error / Skeleton 等）在项目内沉淀并文档化。
- 否决项：Ant Design / shadcn——重或需额外依赖链，本地小面板不值得；Tailwind——实用类方案会增加前端维护面，本项目无既有 Tailwind 资产。

## 第 3–8 层：沿用既有决策（记录）

- 第 3 层 后端语言：Python 3.11+（沿用）。
- 第 4 层 开发框架：FastAPI + Pydantic v2（沿用；面板与 API 同进程，由 `api serve` 托管静态）。
- 第 5 层 数据与存储：SQLite + SQLAlchemy 2.0 + Alembic（沿用；面板不新增存储）。
- 第 6 层 API 契约：沿用 N24 REST + OpenAPI；**记录**：N24 实际未使用 `/v1` 前缀，面板沿用现状不引入（最小改动，OpenAPI 文档即契约）；SSE 实时推送按立项清单后置，MVP 用轮询（间隔可配置，实施阶段定义环境变量）。
- 第 7 层 测试与质量：后端沿用 pytest + ruff + pyright + uv；前端新增 Vitest + React Testing Library（组件 / 逻辑单测）；端到端演示脚本可复现，Playwright 后置。
- 第 8 层 部署与安全：本地 localhost 运行（沿用 N24 默认 127.0.0.1）；无鉴权；密钥规则不变。

## 验收门（第 2 步）

- [ ] 八层逐层有决定，跳过层有理由（无跳过层，均记录）
- [ ] 每个选型有 ADR，否决项有记录
- [ ] 已过「项目与 AI 适配」检查
- [ ] 版本锁定（frontend/package-lock 或 pnpm-lock，实施阶段落定）
- [ ] 用户确认

---

# 前端应用（FE）技术栈决策（2026-08-24）

背景：前端另立独立大项目（docs/project-plan/13-frontend-app-checklist.md，里程碑 W1–W4），立项已由用户确认。本项目在 N12 面板补选之上做八层修订：沿用已落地的继续沿用并记录，立项新要求（SSE 实时推送、全功能界面、Electron 桌面壳）逐层补 ADR。**修订声明**：N12 段落中「SSE 后置、MVP 轮询」与「Playwright 后置」两条被本节修订。

## 第 1 层：前端技术栈（修订）

**决策：React 18 + TypeScript + Vite（沿用 SPA）；新增 React Router（多工作台路由）、TanStack Query（服务端状态与 SSE 失效联动）、Zustand（客户端状态）、react-markdown（Markdown 预览）**

- 候选：沿用 React+TS+Vite / Next.js / Redux Toolkit / SWR / CodeMirror。
- 理由：全功能界面从「三扇窗」长成多工作台，路由与状态管理必须显式化；React Router 生态主流、AI 训练覆盖广；TanStack Query 服务端缓存 / 重试 / 与 SSE 事件失效联动文档成熟；Zustand 轻量，客户端状态（当前作品、抽屉开合）不用 prop drilling；正文编辑器先纯文本 textarea + react-markdown 预览，正文即 Markdown 可读可渲染。
- 否决项：Next.js——本地 SPA + FastAPI 静态托管已定，SSR / 路由文件约定无收益且改动大；Redux Toolkit——样板重，Zustand 覆盖本项目状态量级；SWR——与 TanStack Query 同类，选生态与失效文档更大的后者；CodeMirror / Monaco——代码编辑器向，正文创作场景收益低、包体大，富文本与高级编辑体验后置另议。

## 第 2 层：UI 组件库（修订）

**决策：沿用「不引入重型组件库；自建设计 token（CSS 变量）+ 原生 CSS；图标 Phosphor（统一 strokeWidth）」；组件面扩为侧栏 / 导航 / 表单 / 对话框 / 抽屉 / 树 / 时间线，全部自建并文档化**

- 理由：本地单用户应用、无主题外包需求；自建组件可控、包体小、可定制性拉满；设计体系沿 N12 一致性锁（单 accent、单圆角体系、单一明暗主题、单图标家族），组件库会把体系稀释成混合风格。
- 否决项：Ant Design / MUI——重且视觉同质，主题覆盖成本高；Tailwind——引入第二套样式体系，破坏既有 token 纪律；shadcn——依赖链与构建面增加，自建同样工作量下无净收益。
- 数据可视化：行为时间线 / 耐心池 / 动机强度用轻量自绘（CSS/SVG），不引重型图表库。

## 第 3 层：后端语言与运行时（沿用，记录）

**决策：Python 3.11+（沿用）**——前端项目不改变后端语言；Electron 主进程用 Node，与前端同栈，仅负责窗口与进程编排，不承载业务。

## 第 4 层：开发框架（修订）

**决策：FastAPI + Pydantic v2 + asyncio（沿用）；SSE 实时通道用 sse-starlette（新增）**

- 理由：SSE 是立项拍板的主路径（事件流实时推送），sse-starlette 与 FastAPI 集成好、语义完整（保活 / 游标续传 / 广播），主流且体量小；asyncio 内存队列做单进程 pub/sub 已足够本地单用户。
- 否决项：WebSocket——双向通信本项目不需要，重连与认证成本更高；完全手写 StreamingResponse——可行但保活、断线、多订阅语义要自造，等于自维护一个小库。

## 第 5 层：数据与存储（沿用，记录）

**决策：SQLite + SQLAlchemy 2.0 + Alembic（沿用）**——数据仍由本地 FastAPI 进程持有；Electron 只做壳，不直连 SQLite，避免双进程写库。

## 第 6 层：API 与通信契约（修订）

**决策：REST + OpenAPI（沿用，无 /v1 前缀的现状不变）；写面扩展逐条映射 CLI 命令；SSE 端点带游标续传（Last-Event-ID）；TS 类型由 openapi-typescript 从 OpenAPI 生成**

- 理由：契约先于实现，OpenAPI 是唯一事实源；写面收敛为「CLI 命令 → API 端点」逐条映射，不另造语义；SSE 断线重连靠 EventSource 原生 + 游标，不静默丢事件；类型生成避免手写两遍、杜绝前后端漂移。
- 修订记录：N12 的「SSE 后置、MVP 轮询」撤销——SSE 为本项目主路径（用户拍板），轮询仅作可配置降级。
- 否决项：GraphQL——本地单机查询无复杂度收益；gRPC——浏览器端无原生支持；手写 TS 类型——违反「契约生成、不写两遍」。

## 第 7 层：测试与质量工具链（修订）

**决策：沿用后端 pytest + ruff + pyright + uv；前端 Vitest + React Testing Library + ESLint + tsc；E2E 用 Playwright（从后置升为 W2 起引入）**

- 理由：全功能界面交互面大，单测盖不住主链路；Playwright 覆盖端到端演示与「CLI 与界面同源」对照测试，本地与 CI 同套命令。
- 修订记录：N12 的「Playwright 后置」撤销——W2 起作为 E2E 与对照测试的承载。
- CI：沿用 GitHub Actions（.github/workflows/ci.yml），增加前端四命令 + Playwright 冒烟。

## 第 8 层：部署、可观测性与安全（修订）

**决策：Web 沿用 localhost FastAPI + uvicorn 托管 dist；桌面端用 Electron + electron-builder（Windows 优先，macOS / Linux 尽力而为）；Electron 主进程只开窗口并拉起 / 复用本地服务**

- 理由：桌面壳与 web 同源（用户拍板），一套界面两条入口；electron-builder 打包命令显式化、版本锁定；主进程不承载业务，健康检查失败给可读错误。
- 可观测性：沿用 /health + 结构化日志；SSE 连接状态在界面可见（断线提示 + 自动重连）。
- 密钥与安全：密钥规则不变（环境变量 / 本地配置，永不入库）；单用户 localhost，无鉴权（立项边界）。

## 验收门（第 2 步 · FE）

- [x] 八层逐层有决定，跳过层（第 3/5 层）为沿用记录
- [x] 每个选型有 ADR，否决项有记录
- [x] 已过「项目与 AI 适配」检查（主流、显式、可验证、契约锁定）
- [x] 版本锁定：frontend/package-lock.json 已有；Electron 版本于 W4 实施时锁定
- [ ] 用户确认
