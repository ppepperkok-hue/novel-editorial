# FE-W4 实施真元文档（前端大项目 · 里程碑 W4）

## 总览

- **大阶段**：前端大项目第四个里程碑 W4（立项 docs/project-plan/13-frontend-app-checklist.md，架构 docs/architecture/frontend-app.md）：FE-L 数据管理 + FE-M 设计打磨与 QA + FE-N Electron 桌面壳。
- **W4 一句话**：作者不敲命令行也能导出 / 导入 / 备份作品、改常用配置，整个界面经过设计与 QA 打磨，并可双击桌面应用直接开写。
- **现状**：W1–W3 已收口（后端 1528 测试 + 前端 211 用例）；N25 导入导出 CLI（`works export` / `works import`）与 core.archive 已交付；`GET /config` 只有 panel_poll_interval；无 Electron；无 Playwright E2E。
- **验收总门**：后端 pytest / ruff / pyright 绿 + 前端四命令绿 + CLI/API 同源对照测试 + 演示脚本实跑 + 独立审查归档 docs/reviews/。

## 红线（继承 W1/W2/W3，全阶段强制）

1. 前端只消费 API 契约，不复制业务逻辑。
2. 写面端点与 CLI 命令逐条映射，同源对照测试断言。
3. 三态齐全、错误码与 CLI 对齐，不静默吞错。
4. 最小改动：不翻地基（技术栈 / 目录 / 事件契约 / 表结构），确需改先停下评估。

## 地基影响评估

- 不新增表、不做迁移：导出 / 导入复用 core.archive；配置写面只扩 core.config 服务，不碰 store。
- 依赖新增：后端 `python-multipart`（FastAPI 文件上传）；前端 `frontend/electron/` 独立 package.json（Electron 主进程 + electron-builder）；`frontend/` dev 依赖加 Playwright（E2E）。
- 事件契约不变：导入沿用既有 `workspace_imported` 系统事件，不新造事件。

## 关键决策（总监立项假设，偏离需先回报）

- 配置写面只开放白名单键：quality_threshold / panel_poll_interval / freedom_dial / freedom_seed / proactive_enabled / proactive_max_per_agent / motive_llm_enabled；其余只读，敏感键（LLM key）永不读写。写入 config.toml 后需重启 api 生效，与 CLI `--apply` 语义一致并在响应中提示。
- 导入永不覆盖：与 CLI 一致，生成全新 workspace id 并登记注册表；HTTP 导入用 multipart 上传 ZIP。
- 备份 = 导出归档 + 命名约定：默认目录 `data/backups/<workspace-id>-<YYYYMMDD-HHMMSS>.zip`，前端只做目录与命名，业务仍走导出端点。
- Electron：web 同源，复用 frontend/dist，不复制前端代码；无自动更新、无代码签名；Windows portable + NSIS 优先，macOS / Linux 尽力而为。
- Playwright E2E：FE-M 收口时补，Windows Chromium 主链路 + 数据管理链路 + CLI/UI 同源对照。

## 子阶段 S1：后端契约（数据管理与配置）

### 做什么

- 逐条映射既有 CLI：`works export` → `GET /works/{workspace_id}/export`（ZIP 二进制下载）；`works import` → `POST /works/import`（multipart 上传 ZIP，返回新 workspace，登记 workspace_imported 事件）。
- `GET /config` 扩展为完整只读快照（全部非敏感 Settings 字段，保持 panel_poll_interval 兼容）；新增 `PUT /config` 只写白名单键（见关键决策），core.config 新增通用 `set_config_value`（幂等、保留注释、先 tomllib 校验）。
- 白名单外键或非法值返回 422，与 CLI 错误码语义一致；写后重启生效提示随响应返回。
- OpenAPI 更新 + `npm run gen:types` 重新生成；docs/usage.md HTTP API 节补端点说明。

### 验收标准

- 每端点与 CLI 同源对照测试（导出 ZIP 可被 CLI `works import` 再导入，反之亦然）；错误映射与 CLI 一致；pytest / ruff / pyright / 宪法绿。

### 暂不做

- 前端数据管理界面（S2）；Electron（S3）；Playwright E2E 与打磨（S4）。

## 子阶段 S2：前端数据管理（FE-L）

### 做什么

- features/data：作品导出（下载 ZIP，文件名含作品与日期）、导入（上传校验 + 结果页）、备份（导出到约定目录与命名）、配置界面（白名单键表单 + 只读快照 + 重启生效提示 + 三态）。
- 路由与侧栏入口；与 CLI 同源断言。

### 验收标准

- 前端四命令绿；mock 下导出 / 导入 / 配置读写端到端用例；与 CLI 对照。

### 暂不做

- Electron、Playwright、设计打磨全局项（S3 / S4）。

## 子阶段 S3：Electron 桌面壳（FE-N）

### 做什么

- frontend/electron/：主进程定位后端（`uv run novel-editorial api serve`）、拉起后轮询 /health 就绪、BrowserWindow 指向 localhost、退出时结束子进程；开发 / 生产模式切换；electron-builder 打 Windows portable + NSIS。

### 验收标准

- Windows 上可双击启动、界面行为与 web 一致、退出无残留进程；打包产物可复现。

### 暂不做

- 自动更新、代码签名、安装器之外的发布渠道；macOS / Linux 尽力而为并写清限制。

## 子阶段 S4：QA 收口（FE-M + 全量回归）

### 做什么

- pre-flight 清单（可访问性 / 响应式 / 三态 / 主题一致 / 键盘操作 / 文案一致）逐项核对并修复；Playwright E2E（主链路 + 数据管理链路 + CLI/UI 同源对照）；scripts/w4_demo.py（TestClient：建作品 → 导出 → 导入回环 → 配置读写回环 → DEMO OK）；README 快速开始补桌面端与数据管理说明；全量回归 + 独立审查归档。

### 验收标准

- pre-flight 清单通过；演示脚本可复现；审查链收敛 Ready；后端 pytest / 前端四命令 / smoke / stress / w1-w4 demo 全绿。

## 任务包规划（文件不相交）

- 包 FE-W4-S1：src/novel_editorial/api/app.py + src/novel_editorial/core/config.py + pyproject.toml + tests/test_api.py + tests/test_config.py + docs/usage.md + frontend/src/api 生成产物。
- 包 FE-W4-S2：frontend/src/features/data + 路由 + 侧栏 + 测试。
- 包 FE-W4-S3：frontend/electron/** + 构建脚本 + 文档。
- 包 FE-W4-S4：frontend/e2e/** + Playwright 配置 + scripts/w4_demo.py + README + 文档。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档；地基不动；每个子阶段完成即停、回报四段，经总监确认后再进下一子阶段。

## 状态

- S1 已完成（后端契约：导出 / 导入 / 配置白名单写面；审查收敛 R3 落盘前 TOML 复核，全量回归 1608 测试 + 前端 211 用例全绿）。
- 待办：S2（前端数据管理界面：导出 / 导入 / 备份 / 配置工作台）。
