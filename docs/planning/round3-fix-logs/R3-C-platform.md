六项都修好了mashitawa，编译全过，行为验证六项加多书场景也都过了desuwa。逐个给你对账：

| 编号 | 文件:行号 | 改动摘要 | 验证结果 |
|---|---|---|---|
| R3-C-01 | tools/publish_stock.py:354-373 | 删掉“从存稿书里挑最小 novel_id”的遍历，改成与 current_book.py 一致的活跃书查询（status IN publishing/finishing，取最新一本）；无活跃书时输出 ok:false 加明确错误，不再静默发布 | 多书并存定向验证选中 id=3（最新活跃书）；无活跃书 CLI 输出错误 JSON，不崩 |
| R3-C-02 | tools/publish_stock.py:81-96、379-383 | 新增 _safe_int_setting，pending_publish/daily_chapters 解析失败回退默认值并写 alerts.log 留痕 | 脏配置下输出 ok:true 且 alerts.log 有两条记录，不崩溃 |
| R3-C-03 | tools/preflight.py:38-50 | load_env 真正接收 env_file：指定文件实际加载，已有环境变量仍优先；不传时走原 config.load_env() 路径 | 自定义 env 文件加载成功，预置环境变量不被覆盖 |
| R3-C-04 | tools/collect_reader_stats.py:28-40 | 同上 | 同上 |
| R3-C-05 | tools/get_meta.py:21-38、111、127、129、178、199 | 新增 _safe_json，替换六处无保护的 json.loads（character_states、protagonists、characters state、tags 两处、characters 列表 state），解析失败或类型不符回退默认空结构并写 alerts.log | 脏 tags/protagonists/state 下 CLI 正常输出，默认值生效且留痕 |
| R3-C-06 | tools/record_work.py:230-242 | expected_recover 的 int() 失败回退 seq+10 并写 alerts.log，不中断整次记录 | 脏值下伏笔仍按默认章节插入，留痕存在 |
| R3-C-07 | launch_desktop.vbs:7 | 中文提示改为纯 ASCII 英文，整文件 0 个非 ASCII 字节 | 人工核对：语法结构未动，cscript 不再有 ANSI 解码问题；未实跑以免启动桌面端 |

验证汇总：`python -m compileall` 五个 py 全过；相关测试跑了 publish_stock、preflight_guard、record_work、services_regression、book_isolation、review_v3、review_v4，54 过 2 挂，挂的两个是旧语义用例；editorial_daily 全过。行为自测六项 PASS，全部在临时目录进行，仓库的 alerts.log 没被碰过mashitawa。

额外问题，只报告不改desuwa：

一处是 tests/test_publish_stock.py 的两个 main() 用例（test_publish_success_marks_published_and_logs、test_publish_reports_platform_error）用 status='ready' 构造“可发布书”，而活跃书语义是 publishing/finishing——ready 是建书前的状态，本来就不该发布。这是旧行为留下的测试，建议把这两处（或 make_db 默认值）改成 'publishing'。测试文件不在本包范围，我没动它。

另一处是 tests/test_workday.py 的两个 dry-run 用例失败，对应审查里 editorial P2「dry-run 收工/续工仍写入状态机」（workday.py:306-309）。工作区里 workday.py 已有未完成的修改（_close_locked 在 dry_run 时仍写最终状态），不是本包文件，我没碰。

还有个小观察：get_meta.py:48 的 outline 解析已有 try/except，但只挡解析错误；如果 outline 是合法 JSON 标量（比如 "null"），后续 .get 还是会崩。这不在审查点名的“无保护”清单里，我没动，留给你定夺desuwa。

vbs 那边我选的是 ASCII 英文而不是 BOM，因为纯 ASCII 从根上杜绝解码问题，也比手工塞 BOM 可靠。仓库里没有 MEMORY.md，长期记忆我按惯例记了一条项目进度，别的没动。就这么定了teyo。
