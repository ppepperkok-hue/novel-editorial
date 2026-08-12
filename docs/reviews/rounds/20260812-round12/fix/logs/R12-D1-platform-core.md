六项都修完了mashitawa。先给结论：四个目标文件全部最小 patch，编译、相关测试、行为复现全部验证过，另外发现的问题只报告没动desuwa。

R12-D1-01，[record_work.py](E:/code/novel-editorial/tools/record_work.py:68)：同名合并现在只认两种明确意图——`book_id` 匹配（加了 `ORDER BY id DESC LIMIT 1` 取最新），或 payload 显式带 `merge_by_title: true` 且目标书是 publishing/finishing 活跃连载。其余情况一律插入新书，旧书数据不再被覆盖desuwa。验证：同名 finished 旧书 + 无 book_id → 新行插入、旧书 premise/status 原样；显式 merge 合并进活跃书且不产生重复行；同 book_id 照旧合并，三个场景全过mashitawa。

R12-D1-02，[publish_stock.py](E:/code/novel-editorial/tools/publish_stock.py:104)：新增 `_alert` helper，把 308 行发布复核警告和 331 行完结通知两处裸写入都换成它，OSError 一律吞掉，发布循环不会被日志卡断desuwa。验证：把 ALERTS_LOG 指向目录再调 `_alert`，不抛异常。

R12-D1-03，[preflight.py](E:/code/novel-editorial/tools/preflight.py:54)：`alert()` 补上 try/except OSError，和兄弟 helper 行为一致desuwa。同样用目录模拟不可写，不再崩。

R12-D1-04，[preflight.py](E:/code/novel-editorial/tools/preflight.py:130)：新增 `LOCK_MAX_AGE = 24h`，PID 存活但锁龄超过一天也视为陈旧可回收，PID 复用不再永久卡死desuwa。验证：25 小时前创建的锁配活 PID → 回收成功；新锁配活 PID → 仍拒绝。

R12-D1-05，[check_stock.py](E:/code/novel-editorial/tools/check_stock.py:37)：无活跃书（含 novel_id 查不到）时不再统计全库，stock 直接 0，并返回 `warning: 没有活跃连载作品，未统计库存`desuwa。验证：库里只有完结书带 reviewed 章节，输出 scope=none、stock=0、warning 存在。

R12-D1-06，运行时目录迁移：preflight 的 ALERTS_LOG 和 main 锁路径（30、273 行）、publish_stock 的锁路径（378 行）全部改走 config 的 RUNTIME_ROOT 体系；record_work 六处告警写入（38、51、183、228、322、368 行）也统一用 config.ALERTS_LOGdesuwa。位置说明：editorial_daily.py:562 的日更锁和 control.py:242 的 weekly.lock 仍硬编码 `ROOT / "n8n_tmp"`，这两个文件不在本组允许列表，我没动；control.py:37 的告警早就在用 config.ALERTS_LOG，editorial_daily 的告警走 preflight.alert 已随迁移间接生效desuwa。

验证汇总：`python -m compileall` 四文件通过；相关测试十个文件 105 个全绿；全量测试跑了两轮，第二轮 500 过 2 挂，挂的两个是 round12 已知的 editorial 问题（agent_meeting --dry-run 落库、_review_tone 摩擦方向反），都不在本包范围；第一轮还有两个 editorial_daily 锁占用失败，单独重跑和第二次全量都没复现，我的锁改动只会放宽陈旧回收、不会制造占用，判定是测试顺序性偶发desuwa。手工行为脚本六项全部 PASS，全程用临时数据目录，没碰仓库数据desuno。

额外问题只报不改：一是 editorial_daily.py:562、1681、1748 与 control.py:242、autopilot.py:30 还有 ROOT 硬编码的锁/临时文件/备份路径，需要后续专门一轮迁 config；二是几个测试文件共用 `ROOT/n8n_tmp/t.lock`（test_editorial_daily/test_workday/test_publish_stock），顺序敏感时会互踩，建议测试统一用临时锁目录；三是无 book_id 的 payload 重放现在会创建第二本同名书，这是本次修复的预期取舍，上游应保证带 book_id 或显式 merge_by_title；四是 check_stock 在显式 novel_id 查不到时 warning 文案偏宽泛，不影响行为。测试建议：补 record_work 同名三场景、preflight 锁年龄回退、alert 不可写、check_stock 无活跃书四组用例，测试文件不在指派范围所以我没动mashitawa。MEMORY.md 未更新，本包禁止改其他文件desuwa。
