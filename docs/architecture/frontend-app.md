# 前端应用架构（FE · 独立大项目）

- 建立：2026-08-24
- 定位：前端独立大项目（docs/project-plan/13-frontend-app-checklist.md）的架构 SSOT；与核心架构（rules.md / extension.md）配套，核心规则继续适用，本文只补前端专有约定。N12 面板 MVP 并入本项目作起点，docs/architecture/panel.md 保留为 N12 历史，不再演进。
- 原则：边界先于代码、配置驱动、失败显式化、幂等、最小复杂度；只搭支撑 W1 的最小架构，不搭全量。

## 一、最小架构范围（03a）

### 本期做（支撑 W1 端到端：不敲 CLI 完成一轮创作闭环）

- 面板 MVP 迁移并入 + 全功能壳：React Router 路由、侧栏 / 顶栏、工作台挂载位、SSE 事件通道。
- API 写面（逐条映射 CLI 命令）：works 管理、talk 发送与回放、draft 写 / LLM 生成 / 修订 / 版本、review、decision 三动作、style 基础、structure 基础；SSE 实时事件端点（游标续传）。
- 四个工作台：作品与班子、对话、正文编辑器（纯文本 + Markdown 预览 + 版本对比）、拍板。
- 最小横切能力：API client（openapi-typescript 生成类型）、TanStack Query（服务端状态）、Zustand（客户端状态）、SSE client（断线重连 + 轮询降级）、三态组件基线（loading 骨架 / empty 引导 / error 内联）、错误映射（CLI 错误码 → 界面提示）。

### 本期不做（W2–W4 或立项边界外）

- 结构 / 大纲 / 设定知识 / 灵感、跨作品总览、质量风格工具、自由意志可视化、导入导出、Electron 桌面壳——按里程碑后置，不许顺手搭进 W1。
- 富文本编辑器、SSE 之外的双向实时机制、多用户鉴权、移动端、多人共编、自动发布。

### 范围决策记录

- 范围只到 W1（FE-A / FE-B / FE-C / FE-D / FE-E / FE-F），与里程碑一一对应；「以后可能用到」只留扩展点不写实现。

## 二、通用规则（03b）

### 1. 目录与命名

- `frontend/` 为唯一前端根；`src/` 下：`api/`（客户端 + 生成类型）、`components/`（通用可复用组件）、`features/<工作台>/`（page + 查询 hooks + 工作台专属组件）、`hooks/`、`stores/`、`utils/`。
- 组件 PascalCase `.tsx`；hooks `useX.ts`；测试 `*.test.ts(x)` 与源文件同目录；生成类型只改生成入口，不手改产物。
- 后端写面仍在 `src/novel_editorial/api/`，端点路径与 CLI 命令同构（`talk send` → `POST /works/{id}/talk` 等），命名动词-宾语。

### 2. 依赖方向

- `frontend → API 契约（HTTP + SSE）` 单向；前端不 import Python 包、不直连 SQLite、不复制业务逻辑。
- 后端维持 `api → core → store/llm/quality` 不变，写面只是 api 层扩端点，业务仍下沉 core。

### 3. 错误处理与日志

- API 错误映射 CLI 错误码（业务 / 用法 / 系统 → 1 / 2 / 3），界面按码给内联可读提示；绝不静默吞错。
- SSE 断线：界面可见「连接断开 + 自动重连」状态，游标续传不丢事件；轮询降级可配置。

### 4. 配置

- 前端环境差异（API 地址、轮询降级间隔）走 Vite 构建环境变量，默认 localhost；不硬编码主机端口。
- 密钥一律后端管理（沿用 NOVEL_* 规则），前端不接触、不落库。

### 5. 接口契约

- OpenAPI 是唯一事实源；`openapi-typescript` 从 OpenAPI 生成 TS 类型，禁止手写两遍。
- SSE 事件 payload 复用 `src/novel_editorial/events.py` 事件契约，不另造结构。
- 契约变更：先改后端端点与 OpenAPI，再重新生成类型，CHANGELOG 记录，不静默破坏。

### 6. 测试规则

- 前端：Vitest + React Testing Library（组件三态、关键交互与逻辑）；W2 起 Playwright E2E（主链路 + CLI/界面同源对照）。
- 后端：写面每个端点有契约测试（与 CLI 同源断言），SSE 有订阅 / 重连 / 降级测试。
- 验证门（前端，frontend/ 下）：`npm run lint`、`npm run typecheck`、`npm test`、`npm run build`；后端沿用 pytest / ruff / pyright。

### 7. 代码风格与提交

- ESLint + typescript-eslint；Conventional Commits 英文；可复用组件进 `components/` 并文档化（props、状态、三态）。
- 禁止复制粘贴改命名；每工作台按 features/ 模板接入。

## 三、最小骨架（03c）

- 现状骨架即起点：`frontend/`（Vite + TS 已跑通、39 用例绿）+ `api/app.py` 静态托管 + `/health`。
- W1 骨架落法：路由壳 → API client 与生成类型 → 查询缓存层 → SSE 通道 → 三态组件基线，再逐个接工作台。
- 启动：生产 `uv run novel-editorial api serve`（后端 + 托管 dist）；开发期 `npm run dev`（Vite 代理到本地 API）。
- 验证命令：后端四连 + 前端四命令；干净环境可复现。

## 四、功能接入规则（03d）

### 接入流程

1. 取 FE 单元（13-frontend-app-checklist.md 第 4 层）。
2. 查本文与 rules.md，确认不在「本期不做」清单。
3. 在既有骨架内增量实现：工作台进 `features/`，写面端点进 `src/novel_editorial/api/` 并更新 OpenAPI。
4. 前端单测 + 后端契约测试；跑前端四命令与后端三连。
5. 更新文档（实施文档状态、skeleton 说明），提交走 Conventional Commits。

### 模块模板

- 新工作台：`features/<name>/` = `page.tsx`（路由挂载）+ `use<Name>Queries.ts`（TanStack Query）+ 专属组件；通用交互抽 `components/`。
- API 写面：后端端点 → OpenAPI 更新 → `openapi-typescript` 重新生成 → 前端 client 直接用生成类型。

### 禁止项

- 新工作台自带新框架 / 新状态库；绕过四命令门；复制粘贴改命名；把 W2+ 功能顺手搭进 W1；前端写业务逻辑。

### 每功能交付检查单

- [ ] 与 FE 单元对应，不在「本期不做」清单
- [ ] 规则符合（目录、依赖方向、错误映射、契约）
- [ ] 三态齐全，验收测试覆盖错误路径
- [ ] 前端四命令 + 后端三连全绿
- [ ] 与 CLI 同源对照通过，文档同步，无残留

## 验收门（Phase 0 第 3 步）

- [x] 架构范围只支撑 W1，无全量功能
- [x] 通用规则均有检查手段（lint / 类型检查 / 契约测试 / 模板）
- [x] 最小骨架现状真实跑通（39 用例 + api serve）
- [x] 功能接入模板定义完毕，W1 首单元实测走通
- [ ] 用户确认
