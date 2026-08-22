# 图形面板架构（N12）

## 定位

N12 面板是「老板视角」三扇窗的图形呈现：事件流（实时观察）、穿透查询（看懂伙伴为什么这么判断）、拍板提醒（该我处理就处理）。面板只做观察 + 穿透 + 拍板入口，不写作、不聊天、不共编、不发布。

## 最小架构范围（做 / 不做）

**做（M9 面板 MVP）**：

- N24 API 补口：全局事件流、待拍板清单与拍板三动作、穿透查询（inspect / 草稿 / 版本 / 意见 / 日志 / 设定 / 结构）。
- `frontend/`：React 18 + TypeScript + Vite SPA；构建产物由 `api` 层静态托管；本地 localhost 运行。
- 三扇窗：跨作品概览（含待拍板提醒）、事件流（轮询近实时）、作品穿透抽屉。
- 三态与设计打磨：loading / empty / error 齐备、可访问性、响应式、单设计体系。

**不做（本期）**：

- SSE / WebSocket 实时推送（轮询起步）、面板写作与对话界面、多用户鉴权、移动端、重型图表、Playwright 端到端、模板管理界面。

## 数据源纪律

- 面板每个视图的数据必须可回溯到 N24 API 端点；核心指标（待拍板数、最近事件、作品状态）与 CLI 同一时刻结果一致，用对照测试锁定。
- 数据源不可用时页面显示 error 态并给出来源路径，不拿 fallback 冒充真实数据。

## 前端骨架说明（frontend/）

```text
frontend/
  package.json          # scripts: dev / build / preview / lint / typecheck / test
  package-lock.json     # 提交入库，可复现
  tsconfig.json
  vite.config.ts
  src/
    main.tsx            # 入口
    api/client.ts       # fetch 封装 + OpenAPI 契约类型
    hooks/usePolling.ts # 轮询 hook（间隔可配置）
    components/         # 可复用组件（含三态）
    views/              # 三扇窗页面
  dist/                 # 构建产物（gitignore；由 api 静态托管）
```

- 运行期不需要 Node：`api serve` 直接托管 `frontend/dist`（存在时）；开发期 `npm run dev` 走 Vite dev server。
- 轮询间隔：`NOVEL_PANEL_POLL_INTERVAL`（秒，默认 3，环境变量 / config.toml 均可覆盖）。

## 后继开发性能保障（硬指标）

1. 命令显式：前端 lint / typecheck / test / build 一键可跑，本地与 CI 同一套。
2. 契约即接口：前端类型从 OpenAPI 契约派生 / 手工对齐并锁定，改 API 必须同步前端类型与测试。
3. 组件沉淀：可复用组件进 `components/` 并文档化，禁止复制粘贴改命名。
4. 状态完整：每个视图强制 loading / empty / error 三态，错误显式不静默。
5. 视觉一致：单 accent、单圆角体系、单明暗主题、单图标家族（Phosphor），新增视图沿用 token 不另起炉灶。
6. 依赖克制：新增前端依赖必须有理由并过「项目与 AI 适配」检查，锁定版本。

## 功能接入规则（面板）

新面板视图 = 取单元 → 查本文件与 rules.md → 增量实现（API 补口在 `api/`、组件在 `frontend/src/`）→ 过验证门（后端 pytest / ruff / pyright + 前端 lint / typecheck / test / build）→ 对照测试 + 三态检查 → 提交。

## 验收门

- 三扇窗一屏可达，数据与 CLI 同源（对照测试）
- 前端四命令全绿，构建产物由 `api serve` 托管可复现
- 三态完整、pre-flight 检查通过
- 用户确认
