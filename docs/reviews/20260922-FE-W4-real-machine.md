# 2026-09-22 FE-W4 实机验证收口记录

- 验证方式：真实环境（Windows + 下载 chromium / electron 二进制）
- 范围：Electron 桌面壳打包 + Playwright E2E 实跑
- 依据：AGENTS.md / rules.md / fe-w4-implementation.md / fe-w4-preflight.md

## 实机验证结果（全部通过）

1. **Electron 桌面壳打包**：`cd frontend/electron && npm install && npm run dist` 成功，产出 `release/Novel Editorial Setup 0.1.0.exe`（NSIS）与 `release/Novel Editorial 0.1.0.exe`（portable）。electron 33.4.11 二进制经 npmmirror 镜像下载成功（直连 CDN 受限）。
2. **Playwright E2E**：`npx playwright install chromium`（npmmirror 镜像）成功；`npm run test:e2e` **3 passed**（main-flow 主链路 + data-flow 导出/导入/配置），串行与并行（2 workers）均稳定通过。

## 实机验证发现并修复的 bug

1. **SPA history fallback 缺失**（api/app.py）：深层前端路由（`/works/:id/data`）直接访问返回 404，面板刷新深层页面即 404。修复：`create_app` 加 `/{full_path:path}` catch-all，静态资源优先、否则返回 index.html。
2. **SQLite 并发写锁**（store/db.py）：并发 POST /works 触发 "database is locked"。修复：`_engine` 加 `connect_args={"timeout": 30}` + `PRAGMA journal_mode=WAL`。
3. **alembic 迁移竞态**（store/db.py）：并发创建作品时 `run_migrations` 并发执行，导致 "table workspaces already exists" 与 KeyError 'script'（后端 500 / 崩溃）。修复：`run_migrations` 加 `_migration_lock` 串行化。修复后 12 并发 POST 全 OK、E2E 并行稳定。

## E2E spec 修复

- main-flow：`page.goto("/works")` 命中 API 端点（返回 JSON 非页面）→ 改为从根路径 `/` 经侧栏导航。
- data-flow config：默认键 quality_threshold 填了 `0.75`（非法，应为整数）→ 改为 `10`。

## 遗留（非阻塞）

- `test_sse` 根因已闭环：非代码回归，而是操作残留（残留 python 进程 + config.toml 被 E2E 写面污染 8→10）；清理后 test_sse 5 passed、后端全量 pytest 1612 passed 全绿。
- Electron 双击验证已闭环：`npm start` 定位项目根 → spawn 后端 → 轮询 health → 开窗（标题「Novel Editorial 面板」）；`CloseMainWindow` 正常关闭后 electron 与后端进程树零残留。

## 处理记录

- 代码提交 73d6c0b（SPA fallback + 迁移锁）、8a23e86（E2E spec 修复）、9474f21（gitignore + electron lockfile）、0561a2f（P3 remainder），已推送 origin/main。
