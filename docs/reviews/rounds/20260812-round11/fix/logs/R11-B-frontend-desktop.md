弄好了mashitawa。五条修复全部落地，验证也跑完了desuwa。

R11-B-01，只读安装目录下的静默失败，我分两层处理。`novel_editorial/config.py` 第7-9行加了 `RUNTIME_ROOT`，第21-23、28-29行把 `TMP_DIR`、`EXPORTS_DIR`、`DATA_DIR`、`ALERTS_LOG`、`HOT_TOPICS_JSON` 全部改挂到它下面；`desktop/main.js` 第76-117行新增 `runtimeDataDir` 和 `dataDirProblems`，第115行启动后端时把 `NOVEL_DATA_DIR` 指向 userData，第403-419行在启动时逐个探测这些目录能否写入，写不了就弹错误框并退出，不再假装成功desuwa。验证：node --check 通过，config 的 env 覆盖和默认回退都实测过，py_compile 通过mashitawa。

R11-B-02，`desktop/release.js` 现在发布前自动 bump。第30-57行是 semver 解析、比较、bump 函数，第64-76行默认 patch +1，也支持 `--minor`、`--major`、`--version=x.y.z`、`--no-bump`；第85-94行先查 GitHub 最新 release，版本不高于远端就拒绝发布，第111-113行在 dist 之后校验 latest.yml 的 version 与 package.json 一致，不一致直接中止desuwa。`main.js` 第378行启动时打印当前版本，第380-383行给 autoUpdater 挂了 error 日志，更新失败不再无声无息desuno。package.json 本身没动——版本就是留给 release.js 在发布时写的，JSON 校验已通过mashitawa。

R11-B-03，AgentsPage 的心情草稿现在锁定编辑时的 agent。第52行加 `moodDraftAgentRef`，第142-145行每次编辑草稿都记下归属，第147-161行保存前先核对归属，切走之后再点保存会被拒绝并提示；第106-112行切换时清空草稿与归属，第95-105行 dirty 状态把草稿也算进去，带着草稿切换会先弹确认框desuwa。验证：vitest 8 个文件 20 条用例全过，build 也过了mashitawa。

R11-B-04，`main.js` 第26-27行加冷却期常量和时间戳，第131-139行每次异常退出时先检查，距上次崩溃超过 10 分钟就把重启计数清零，自愈预算自动恢复，不需要手动重置desuwa。

R11-B-05，config.py 的 `load_env` 本来就走 `_strip_inline_comment`，问题在 `main.js` 的 panelToken 自己重新解析却忘了剥注释。第232-243行补了和 Python 端同规则的 `stripInlineComment`，第252行应用它，托盘请求不会再带着 `xxx # comment` 吃 403 了mashitawa。config.py 这边无需再改，我用临时 .env 验证过：`PANEL_TOKEN=sekret123 # comment` 解析出来就是 `sekret123`desuno。

额外问题，只报告不改desuwa。`services/control.py:242`、`tools/editorial_daily.py:561` 的锁路径和 `tools/preflight.py:30` 的告警日志路径还硬编码在 ROOT 下，只读安装这次靠启动探测拦住了，但真正挪到 userData 得改那三个文件，超出本包范围desuno。desktop 的 `api-error` 通道 main.js 一直在发，preload 和 webapp 却没有桥接，桌面侧错误到不了页面desuwa。release.js bump 后 `desktop/package-lock.json` 的根 version 会短暂不同步——该文件不在允许列表里我没动，npm ci 不比对版本字段，之后一次 npm install 会自己对齐。AgentsPage 的 saveDiary 在异步完成后用当时的 `selected.file` 刷新列表，保存中切 agent 会刷错列表，写入本身按 diary id 是安全的desuno。构建还有那个 charts 分块 527 kB 的旧警告，非本轮引入mashitawa。

测试建议照列：AgentsPage 补「编辑A心情→切B→确认丢弃→断言绝不带A草稿写B」的用例；config 补 `NOVEL_DATA_DIR` 覆盖和行内注释用例；release.js 用 mock 的 gh 测陈旧版本拦截；main.js 测 `stripInlineComment` 和冷却重置。MEMORY.md 未涉及，没有更新mashitawa。
