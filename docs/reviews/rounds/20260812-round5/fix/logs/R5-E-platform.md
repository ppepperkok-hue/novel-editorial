修完了mashitawa，六项全部落地，先说结果：编译全过，相关测试 67 过 1 失败，那个失败是我要重点交代的desuwa。

`tools/create_book.py` 的性别判定（第 57-58 行关键词表、第 95-98 行 `_gender`）把男频特征词从「仙侠、玄幻、武侠、都市、科幻」这些中性题材词换成了「男频、无敌、赘婿、战神、后宫、种马」这类显式标记。现在「仙侠言情」「都市言情」「玄幻言情」都判女频 0，「都市」「悬疑灵异」这些没有女频特征的仍判男频 1。我直接用 Unicode 转义绕过控制台编码跑了八组断言，全对mashitawa。

`tools/collect_reader_stats.py` 第 86-111 行改成 DB 权威：先查 publishing/finishing 的最新一本拿 book_id，`FANQIE_BOOK_ID` 只作兜底，两者皆无就明确返回错误。我 mock 了三组场景验证——DB 有书时用 DB 的、DB 无书时用环境变量的、都没有时不发请求直接报错，都符合预期desuwa。

`tools/record_work.py` 第 7 行加了 argparse，第 469-480 行补上 `--db`（默认仍是仓库根下 demo.db），`--file` 和 base64 两种输入都保留。我用临时库实测了三趟：base64 参数、`--file`、缺参数报错，中文书名正确写入指定库，没有碰真实 demo.db，这手不亏desuwa。

`tools/preflight.py` 第 209-211 行把 `--no-lock` 死参数删了——CLI 本来就是纯检查、从不持锁，保留那个参数只会误导人。`--help` 里已经看不见它，真实跑了一次无凭据预检，快速失败、退出码 0、不写锁，行为没变desuwa。

`scripts/install_autostart.ps1` 第 102-104 行改用 `UTF8Encoding($true)` 加 BOM 写 VBS，PowerShell 5.1 也能识别，非 ASCII 路径不再被替换成问号。脚本过了语法解析，`-DryRun` 也正常跑了一遍desuwa。

环境那边，`.venv` 装好了 `websocket-client==1.9.0`（与 uv.lock 一致），`import websocket` 实测成功。另外 `python -m compileall` 四个工具全过；`test_create_book`、`test_record_work`、`test_preflight_guard`、`test_services_regression` 一起 38 过，`test_review_v4`、`test_audit_evolution`、`test_knowledge_bible`、`test_review_v3` 29 过。

唯一那个失败在 `tests/test_create_book.py:77`，它断言「玄幻言情→1 男频关键词优先」，正是审查点名要改的旧语义。新规则下玄幻言情是女频，断言自然失效，但测试文件不在我的允许修改列表里，所以我没动它，这点请您定夺：要么让对应分片更新这条断言，要么授权我改。额外还有三件事只报告不改：删除 `--no-lock` 后，若还有遗留 n8n 工作流传这个参数会直接报错退出，不过仓库里已搜不到调用方；collect_reader_stats 无活跃书时的行为从「发空 book_id 请求」变成明确报错，是刻意为之；还有工作区里其他分片的 agent 正在并行改一批文件，我只碰了指派的五个，`MEMORY.md` 不在允许范围也没有更新desuwa。
