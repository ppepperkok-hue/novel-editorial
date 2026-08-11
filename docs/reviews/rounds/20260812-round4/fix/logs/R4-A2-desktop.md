四项目都修完，验证也过了mashitawa。逐项说desuwa。

R4-A2-01：`desktop/main.js:55`。打包模式不再把 DB 复制到 `userData`（C 盘），统一用 `path.join(ROOT, "demo.db")`，与后端 `config.DB_PATH` 完全一致。后端 `control.py:290` 的 `relpath(_db_path(), ROOT)` 因此同盘返回 `demo.db`，非 C 盘安装不会再抛 ValueError。我实测复现了旧路径的 `path is on mount 'C:', start on mount 'E:'`，再验证新路径返回 `demo.db`，ps1 侧 `Join-Path` 也正确拼到 `ROOT\demo.db`，链路对上了desuwa。

R4-A2-02：`desktop/release.js:34`。`npm run dist` 之前先 `npm run build`（cwd 指向 `webapp/`），execSync 构建失败会直接抛错、进程非零退出，发布自然中止。没实跑发布，只做了语法检查desuno。

R4-A2-03：`desktop/main.js:198-205`。终态列表加入 `partial`，通知文案分成三档：成功 / 部分成功 / 失败，部分成功不再静默mashitawa。

R4-A2-04：`desktop/main.js:120-142`。新增 `panelToken()`，优先读进程环境，其次读 `~/.n8n/.env`，与后端 `web_api._panel_token()` 的解析顺序一致；托盘 POST 现在带 `Authorization: Bearer <token>`，配置 PANEL_TOKEN 后不再 403desuwa。

验证结果：`node --check desktop/main.js desktop/release.js` 双双通过；release.js 没有测试可跑；跨盘问题用 Python 模拟确认已消除。只动了两个指派文件，没碰 gitdesuwa。

额外发现两个，只报不改。一个是 DB 移到安装目录后，`extraResources` 里打包的种子 `demo.db` 在应用更新时可能覆盖用户数据，而且安装目录若不可写（比如被选到 Program Files）保存设置会再次失败——根治该在后端 relpath 或用户数据目录设计，本包范围够不着desuno。另一个是 `triggerWorkflow` 的 catch 分支仍然只写 console，网络失败时托盘没有任何用户提示，和 R4-A2-04 的"静默失败"同类desuwa。
