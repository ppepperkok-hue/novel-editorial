# M5 实施真元文档（产品形态与开源 · N24 API 服务层）

## 总览

- **大阶段**：M8 产品形态与开源扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N20/N21/N22 已收口，N24 为下一 P1 候选）。
- **N24 一句话**：同一个编辑部能力，多一扇门——HTTP API 与 CLI 同源，面板（N12）与外部工具不再重复造轮子。
- **现状**：
  - CLI 已覆盖 works / style / quality / events / structure / overview 等入口；core 层函数可直接复用；
  - 无 HTTP 入口；面板与外部工具目前只能走 CLI 子进程或重复实现业务逻辑。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「TestClient 起 app → POST /works 建作品 → GET /works/{id} 可见 → GET /works/{id}/events 为空 → 作品不存在 404」；既有 1019 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **CLI 同源不复制**：API 只调 core / store / quality 既有函数，不复制业务逻辑；同一数据同一时刻 API 与 CLI 结果一致。
2. **只读优先**：本阶段写操作仅 `POST /works`（复用 `create_workspace` 既有行为）；其余路由全部只读，不落事件、不触发 proactive。
3. **本地优先**：默认绑定 `127.0.0.1`，无鉴权（个人本地工具）；文档明示不得直接暴露公网。
4. **错误映射显式**：`NovelError` → HTTP（NOT_FOUND→404、USAGE_ERROR→422、其余→500）；未捕获异常→500；响应体统一 `{"detail": ...}`。
5. **配置驱动**：host / port 走 `NOVEL_API_HOST` / `NOVEL_API_PORT`（TOML 默认 `api_host` / `api_port`），默认 `127.0.0.1:8765`，不硬编码。
6. **面板不反向绑架**：本阶段不做 SSE / 事件订阅；N12 面板后置，按需再议。

## 地基影响评估（先评估再动工，用户已确认框架方向）

- **新增运行依赖**：fastapi、uvicorn；**新增 dev 依赖**：httpx（FastAPI TestClient 需要）。`pyproject.toml` 与 `uv.lock` 用 `uv add` 更新（S1 允许触碰）。
- **新增目录**：`src/novel_editorial/api/`（镜像 cli 的入口层；依赖方向 `api → core → store/llm/quality`，api 不得 import cli）。
- **配置新增**：`core/config.py` 的 `Settings` 增 `api_host` / `api_port` 字段并在 `load_settings` 读取（端口 1–65535 校验，非法抛 CONFIG_ERROR）；无表结构变更、无事件契约变更。
- **CLI 新增**：`api serve` 子命令（`cli/app.py` 注册 api 组，`cli/api.py` 作薄壳调 api 层）。
- **依赖守卫**：`tests/test_deps.py` 的禁止层列表补 `api`（api 不得 import cli）。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：骨架、配置与基础路由

### 做什么

- 依赖：`uv add fastapi uvicorn`、`uv add --dev httpx`（更新 pyproject.toml 与 uv.lock）。
- `core/config.py`：`Settings` 增 `api_host: str = "127.0.0.1"`、`api_port: int = 8765`；`load_settings` 读 `NOVEL_API_HOST` / `NOVEL_API_PORT`（TOML `defaults.api_host` / `defaults.api_port` 兜底，端口 1–65535，非法抛 NovelError(CONFIG_ERROR)）；`tests/test_config.py` 补用例。
- `api/app.py`：`create_app() -> FastAPI`——异常处理器把 `NovelError` 映射为 HTTP 状态（NOT_FOUND→404、USAGE_ERROR→422、其余→500），响应体 `{"detail": ...}`；路由使用既有 core 函数，不复制业务逻辑。
- 基础路由：
  - `GET /health` → `{"status": "ok"}`；
  - `GET /works` → 作品数组（id / title / genre / description / status / created_at）；
  - `POST /works` → 创建作品（body：`title` 必填，`genre` / `description` 可选；复用 `core.workspace.create_workspace`；成功 201 + 作品对象）；
  - `GET /works/{workspace_id}` → 作品详情 + band（agents 数组，字段与 `works show` 一致口径）。
- `cli/api.py` + `cli/app.py` 注册：`api serve [--host HOST] [--port PORT]`——`uvicorn.run(create_app(), host=..., port=...)`，命令行选项覆盖配置。
- `tests/test_deps.py`：禁止层列表补 `api`。
- `tests/test_api.py`（FastAPI TestClient）：health、works list / create / show、作品不存在 404、非法端口配置 CONFIG_ERROR、GET 类路由不落事件。

### 做到什么程度

- HTTP 服务可起、基础路由可用、错误映射正确、配置驱动；CLI 与 API 同源可验证。

### 验收标准

- 单测覆盖上述全部路径；依赖守卫通过；既有 1019 测试零回归。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- 其余路由（S2）、鉴权、SSE、HTTPS、公网部署文档。

## 子阶段 S2：编辑部可见性路由

### 做什么

- 只读路由（全部复用既有 core 函数，不落事件、不触发 proactive）：
  - `GET /overview` → 跨作品聚合（复用 `core.overview.build_overview`）；
  - `GET /works/{workspace_id}/events` → 事件数组（复用 `store.events.list_events`）；
  - `GET /works/{workspace_id}/style` → 风格锚点（description / forbidden_words，复用 `core.style.get_style_anchor`）；
  - `GET /works/{workspace_id}/structure` → 结构节点数组（id / kind / title / parent_id / sort_order / status / draft_id，复用 `core.structure.list_structure`）。
- `tests/test_api.py` 追加：各路由端到端 + 只读断言（events 数不变、不新增任何行）+ 作品不存在 404。

### 做到什么程度

- 面板与外部工具可读的可见性面齐了；写面保持最小（仅 works create）。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 写操作（除 works create）、quality / consistency 在线命令、SSE、鉴权。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- `docs/usage.md` 增「HTTP API（N24）」小节：启动命令、host / port 配置、路由表、错误码映射、本地绑定安全说明、curl 示例 mock 实跑。
- `docs/architecture/rules.md` 目录约定补 `api/` 一行；`config.example.toml` 如有则补 `api_host` / `api_port` 注释行。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260821-M5N24S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 1019+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 鉴权、SSE / Webhook、OpenAPI 深度定制、公网部署、N12 面板集成。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权低价窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-21）：实施文档就绪；用户已确认框架方向（FastAPI + uvicorn）；拆包 S1。
