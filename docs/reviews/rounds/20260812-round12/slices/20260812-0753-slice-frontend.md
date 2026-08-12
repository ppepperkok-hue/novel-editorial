基线构建与语法检查全部通过；webapp 前端与后端接口契约逐项核对匹配（含 control/dashboard/meetings/ending/agents/activity/export/flow/daily_runs/ai_taste/agent_states），错误处理与审计日志完备，未发现 P0/P1 级阻塞缺陷。发现的问题均为 P2/P3 级别的部署边界与一致性瑕疵。

Full review comments:

- [P2] 桌面版锁文件仍写入安装目录，未随 NOVEL_DATA_DIR 迁移，只读安装导致应用拒绝启动 — E:\code\novel-editorial\desktop\main.js:82-93
  `desktop/main.js` 的 `dataDirProblems()`（第 82-93 行）要求 `ROOT/n8n_tmp` 可写，否则启动即退出，原因是后端锁文件没有跟随 `NOVEL_DATA_DIR` 抽象迁移：`novel_editorial/config.py:9` 已定义 `RUNTIME_ROOT`（`TMP_DIR = RUNTIME_ROOT / "n8n_tmp"`），但 `novel_editorial/services/control.py:242` 的 `weekly.lock` 与 `tools/editorial_daily.py:562` 的每日锁仍硬编码 `ROOT / "n8n_tmp"`。后果：桌面版经 NSIS 以“为所有用户安装”装进 Program Files（`package.json` 的 nsis 配置允许选择安装目录）时，锁目录不可写，应用直接弹错误框退出、完全不可用；per-user 安装时锁文件会残留在安装目录，升级覆盖可能造成锁残留。建议把两处锁路径改用 `config.TMP_DIR`，`dataDirProblems` 就不再需要检查 ROOT 可写。

- [P3] release.js 的陈旧版本检查在 gh 失败时静默失效，可能重建同版本 Release — E:\code\novel-editorial\desktop\release.js:83-89
  `desktop/release.js` 第 83-89 行：`gh release view latest` 抛错被空 `catch` 吞掉，`latestRemote` 保持空串，`compareVersions` 的防陈旧保护被跳过。在 gh CLI 认证失效或网络故障时，发布流程会继续执行 `release delete` + `release create`，重建与线上同版本的 Release（`electron-updater` 因版本号未递增不会升级客户端，但线上 latest 被覆盖、历史资产被替换）。建议 gh 查询失败时中止发布而非静默继续。

- [P3] CommandPalette 触发 run-daily/run-weekly 后不刷新面板数据，与其它操作不一致 — E:\code\novel-editorial\webapp\src\components\CommandPalette.jsx:63-72
  `webapp/src/components/CommandPalette.jsx` 的 `runAction` 中，`run-daily`/`run-weekly` 分支（第 63-72 行）`pushToast` 后直接 `return`，没有像 `pause/resume` 分支那样调用 `onRefresh()`。用户用 Ctrl+K 手动触发日更/周会后，仪表盘、执行记录等依赖 5-30 秒轮询才看到新状态，而同样的“立即运行”按钮在 Dashboard/Settings 页面都会主动刷新。建议补上 `onRefresh()` 保持一致。

- [P3] 桌面端 api-error IPC 与 preload closeToTray 均为无消费方的死代码 — E:\code\novel-editorial\desktop\main.js:127-143
  `desktop/main.js` 第 127、143 行在 API 崩溃/退出时 `win.webContents.send("api-error", ...)`，但 `webapp/src` 全量检索没有监听 `api-error` 的处理器，前端不会收到任何崩溃提示（目前仅靠系统 Notification 兜底）；`desktop/preload.js:11` 暴露的 `closeToTray()` 在 webapp 中也没有调用方（SettingsPage 只用了 `quit()`/`setAutoLaunch`）。建议删除或补齐对应监听，避免误导后续维护者。
