四项都处理完了，验证也全过了，我一项项说desuwa。

R12-B-01（[desktop/main.js](/abs/path/desktop/main.js:82)）：`dataDirProblems()` 里对 `ROOT/n8n_tmp` 的可写探测和对应注释删掉了，可写检查现在只覆盖 userData 下的 `base`、`exports`、`demo_data`、`n8n_tmp`，与 `runtimeDataDir()` 一致。桌面端不再因为安装目录只读而拒绝启动mashitawa。

R12-B-02（[desktop/release.js](/abs/path/desktop/release.js:83)）：`gh release view latest` 的 catch 分支从静默放行改成抛错中止，错误信息带 `err.stderr` 或 `err.message`，发布流程在版本检查失败时直接失败，不再可能漏查后重建同版本 Release。

R12-B-03（[webapp/src/components/CommandPalette.jsx](/abs/path/webapp/src/components/CommandPalette.jsx:63)）：run-daily/run-weekly 分支在 `pushToast` 之后补了 `onRefresh()`，与 pause/resume 入口行为一致，执行完立刻刷新面板。

R12-B-04（[desktop/main.js](/abs/path/desktop/main.js:117)）：核实过 preload.js 只暴露 `closeToTray`，webapp 没有任何 api-error 监听或 closeToTray 调用，两个通道都是无消费方。删了 main.js 里两处 `win.webContents.send("api-error", ...)`（spawn error 与 exit 分支）和 `app:close-to-tray` 的 ipcMain 注册；后端异常仍走系统通知 `notifyIssue`，用户不会失去提示。preload.js 不在本次允许清单里，`closeToTray` 桥接保留未动。

验证结果：`node --check desktop/main.js desktop/release.js` 通过；webapp 里 `npx vitest run` 8 个文件 20 条用例全过；`npm run build` 成功，只有既有的 charts 分包 527 kB 体积警告。

额外发现，只报告不改：L-068 的核心其实还在后端——`novel_editorial/services/control.py`（weekly.lock）、`tools/editorial_daily.py:562`、`tools/preflight.py`、`tools/workday.py`、`tools/publish_stock.py`、`tools/release_lock.py` 仍硬编码 `ROOT / "n8n_tmp"`，没切到 `config.TMP_DIR`。桌面侧不再拦截只读安装，但锁文件实际落盘位置要真正迁移到 userData，得改那些 Python 文件，超出本包范围desuno。另外工作区里 `novel_editorial/web_api.py`、`tools/daily_runs.py`、`tools/record_work.py` 有我没动过的未提交改动，应该是并行任务留下的，我没有碰它们mashitawa。
