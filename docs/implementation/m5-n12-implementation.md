# M5 实施真元文档（产品形态 · N12 图形面板）

## 总览

- **大阶段**：M8 产品形态扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md 与 08-n12-panel-checklist.md；N24 API 已收口，N12 为 06 清单最后一项）。
- **N12 一句话**：三扇窗一屏可达——事件流、穿透查询、拍板提醒，N24 API 同源，面板是窗户不是产品本体。
- **现状**：N24 API 已有 /works /overview /events /style /structure；缺口是待拍板读写、穿透查询（inspect / 草稿 / 版本 / 意见 / 日志）与前端本身。
- **验收总门**：后端验证四连全绿 + smoke_m3 + stress_m3 + 前端 lint / typecheck / test / build 全绿；至少一条端到端「api serve 起面板 → 三扇窗数据与 CLI 对照一致 → 面板拍板 → CLI 与面板同时可见新状态」；既有 1147 测试全绿。

## 红线（本阶段强制，08 立项清单 + 架构 panel.md 继承）

1. **数据同源**：面板只消费 N24 API，不复制业务逻辑；同一时刻面板与 CLI 结果一致（对照测试）。
2. **只读优先**：写操作仅拍板三动作（accept / reject / note），其余全部只读。
3. **三态完整**：每个视图必须有 loading / empty / error 三态，错误显式不静默。
4. **视觉一致**：单设计体系、单 accent、单圆角、单明暗主题、单图标家族（Phosphor）；可访问性与响应式达标。
5. **后继开发性能**：前端四命令（lint / typecheck / test / build）本地与 CI 同一套；契约以 OpenAPI 为准；组件沉淀文档化；轮询间隔可配置（NOVEL_PANEL_POLL_INTERVAL，默认 3）；Node 仅开发期，运行期由 `api serve` 托管 dist。

## 地基影响评估（先评估再动工）

- 新增 `frontend/`（React 18 + TS + Vite + Vitest + ESLint；npm + package-lock 提交入库）；`api/app.py` 用 fastapi.staticfiles 托管 `frontend/dist`（存在时）。
- N24 API 补口（decision pending / 拍板写操作 / inspect / drafts / reviews / log / 全局事件流），全部复用既有 core 函数；写操作收敛为决策三动作。
- `core/config.py` 增 `panel_poll_interval`（NOVEL_PANEL_POLL_INTERVAL，1–300 秒校验）。
- 无表结构变更、无事件契约变更、无新 Python 依赖。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：API 补口（U27-A）

### 做什么

- `api/app.py` 新增（全部复用 core / store 函数，错误映射与既有一致）：
  - `GET /events`：跨作品事件流——以全局 workspaces 注册为源（与 /works /overview 一致），逐作品取事件按时间倒序合并，返回 `{"events": [...], "skipped": N}`；单作品读取失败跳过并计数，不拖垮整条流；
  - `GET /works/{id}/pending`：待拍板草稿列表（复用 `list_pending_drafts` + 版本摘要）；
  - `POST /works/{id}/decisions`：body `{draft_id, action: accept|reject|note, content?}`，复用 `core.decision.decide`；写操作仅此三个动作；
  - `GET /works/{id}/inspect?keyword=`：复用 `search_all_layers`，返回 text/plain 原样文本（与 CLI 同源，面板直接显示）；
  - `GET /works/{id}/drafts` 与 `GET /works/{id}/drafts/{draft_id}`：草稿列表 / 详情（含版本数组）；
  - `GET /works/{id}/reviews?draft_id=`：意见列表；
  - `GET /works/{id}/log`：复用 `build_workspace_log`，返回 text/plain 原样文本（与 CLI log 同源）。
- tests（`tests/test_api.py` 扩展）：各端点端到端 + 404 / 422 / 只读断言（除 decisions 外 events 数不变）+ 拍板后状态流转 + 全局事件流排序。

### 做到什么程度

- 面板所需的全部读数据与拍板写操作都有 API；CLI 同源。

### 验收标准

- 端点单测 + 失败路径；对照测试（API 与 CLI 同数据）。

### 验证方式

pytest + ruff + pyright + 宪法。

### 暂不做

- 前端（S2）、SSE、鉴权。

## 子阶段 S2：前端骨架（U27-B）

### 做什么

- 修复 S1 独立审查两个 P2（允许触碰 api/app.py 与 tests/test_api.py）：
  - `inspect` / `log` 改用 `PlainTextResponse(media_type="text/plain")`，杜绝 FastAPI 把文本包成转义 JSON 字符串；
  - `GET /events` 改为以全局注册为源、逐作品失败隔离（stderr 警告 + skipped 计数），返回 `{"events": [...], "skipped": N}`。
- `frontend/` 脚手架：package.json（react / react-dom / typescript / vite / @vitejs/plugin-react / vitest / @testing-library/react / jsdom / eslint + typescript-eslint）、tsconfig、vite.config、`src/main.tsx`；
- scripts：`dev` / `build` / `preview` / `lint` / `typecheck` / `test`；
- `api/app.py` 静态托管 `frontend/dist`（存在时 `GET /` 返回 index.html；目录路径可用 `NOVEL_FRONTEND_DIST` 环境变量覆盖，默认仓库 `frontend/dist`，测试隔离用）；
- `core/config.py`：`panel_poll_interval`（默认 3，1–300，CONFIG_ERROR 校验）+ 测试；
- 占位首页（三扇窗容器骨架）+ 前端单测（渲染占位页、配置读取）；
- README / docs 记录前端命令（Node 仅开发期）。

### 做到什么程度

- 一条命令起面板看到骨架页；前端四命令全绿可复现。

### 验收标准

- 后端 `GET /` 返回托管页面（dist 存在时）；前端四命令绿；配置用例绿。

### 验证方式

pytest（新增）+ 前端四命令 + ruff + pyright + 宪法。

### 暂不做

- 三扇窗数据（S3）、设计打磨（S4）。

## 子阶段 S3：三扇窗 MVP（U27-C）

### 做什么

- `frontend/src/api/client.ts`：fetch 封装 + 契约类型；`hooks/usePolling.ts`（间隔读 NOVEL_PANEL_POLL_INTERVAL 或前端常量默认 3 秒；MVP 前端常量 + 后端配置暴露 /health 或 /config? 决定：前端常量 3 秒，后端配置项留待面板设置；S2 已加 config，前端读 `/health` 不需要；简单起见前端常量 DEFAULT_POLL_INTERVAL_MS=3000，文档记录）。
- `api/app.py` 新增 `GET /config` → `{"panel_poll_interval": N}`（只读，复用 settings），前端启动时读取并用作轮询间隔（配置驱动落地，不再只靠前端常量）。
- 三扇窗：
  - 顶部跨作品概览（`GET /overview`）：作品卡（标题 / 状态 / 待拍板数 / 进度 / 最近活动），点击进穿透；
  - 事件流（`GET /events`）：最新在前，自动轮询，事件行可点击跳作品；
  - 待拍板清单（`GET /works/{id}/pending`，全部作品聚合）：该处理就处理；
  - 穿透抽屉：作品下分层查看（inspect 检索 / 草稿与版本 / 意见 / 日志 / 设定 / 结构 / 风格）。
- 三态组件：Skeleton / Empty / Error（含来源路径提示）。
- 测试：组件与 hook 单测（mock fetch）；轮询节流与错误态。

### 做到什么程度

- 三扇窗一屏可达，数据与 CLI 对照一致。

### 验收标准

- 端到端演示（api serve + HTTP 断言三扇窗数据源）+ 组件单测；对照测试。

### 验证方式

前端 lint / typecheck / test / build + pytest（对照）+ 冒烟。

### 暂不做

- 拍板接线（S4）、SSE、移动端。

## 子阶段 S4：拍板操作与设计打磨（U27-D / U27-E）

### 做什么

- 修复 S3 独立审查三个 P3（允许触碰 frontend/src/** 与 frontend/vite.config.ts、frontend/src/**测试）：
  - 草稿切换时旧版本残留：仅在 `detail.data.id === selectedId` 时渲染版本列表（或请求开始时清空 data）；
  - 抽屉切换作品保留旧选中态导致 404：为抽屉加 `key={workspace.workspace_id}`（或 workspace 变化时重置 activeTab / selectedId）；
  - `npm run dev` 请求打不到后端：vite.config.ts 配 `server.proxy`，将 `/health /config /works /overview /events` 代理到 `http://127.0.0.1:8765`（target 可用 `VITE_API_TARGET` 覆盖，默认同上）。
- 待拍板项操作：accept / reject 按钮 + note 可选输入 → `POST /works/{id}/decisions` → 刷新清单与事件流；确认交互防误触；操作后 CLI 与面板同时可见新状态。
- 设计打磨：单 accent token 体系、响应式、可访问性（焦点管理、aria、对比度）、pre-flight 清单逐项过。
- 端到端演示：`scripts/panel_demo.py`（临时数据目录 → seed → api serve 起服 → HTTP 断言三扇窗与拍板流转 → 停服清理）或等价可复现脚本。

### 做到什么程度

- 面板内完成「看 → 穿透 → 拍板」闭环；视觉与可访问性达标。

### 验收标准

- 拍板端到端（面板操作 → 双通道可见）；pre-flight 清单通过；演示脚本可复现。

### 验证方式

前端四命令 + pytest（拍板对照）+ 演示脚本 + 设计审查。

### 暂不做

- SSE、对话发送、模板管理。

## 子阶段 S5：文档、全量回归与收口

### 做什么

- 修复 S4 独立审查 P3（允许触碰 src/novel_editorial/store/db.py、scripts/panel_demo.py 与 tests/）：`DB` 增加公开 `dispose()`（释放全局与全部作品引擎并清空缓存），演示脚本改用之，不再摸私有 `_workspace_engines`。
- usage.md 增「图形面板（N12）」小节（启动、三扇窗、拍板、配置、Node 仅开发期说明）；README 快速开始补面板。
- 全量回归：pytest 全量 + smoke_m3 + stress_m3 + 前端四命令 + 演示脚本。
- 独立审查 + 归档 docs/reviews/（20260822-M5N12S1 … S5 链）；progress 与 07-backlog 收口。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 1147+ 测试与前端四命令全绿，审查链收敛。

### 验收标准

- 文档示例实跑生效；审查链收敛；06 清单仅剩 N12 一项转为完成。

### 验证方式

pytest + 前端四命令 + smoke_m3 + stress_m3 + 宪法 + 演示脚本。

### 暂不做

- SSE 实时推送（后置）、Playwright 端到端、移动端。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权低价窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-22）：Phase 0 立项清单与技术栈 ADR 已确认；架构（panel.md + rules.md 补前端规则）就绪；拆包 S1。
