修完了mashitawa。五项都落地，验证也跑完了，听我慢慢说desuwa。

先讲结论：五个指派文件只动了该动的地方，别的文件一概没碰，MEMORY.md 也不在允许范围内，所以没更新desuno。

R10-B-01，[publish_stock.py](/E:/code/novel-editorial/tools/publish_stock.py:426)：`--chapters` 分支补了 `pending = 0` 防止变量悬空；发布后的清零改成按实际发布数递减，`max(0, pending - published)` 回写 settings。pending=12 只发了 10 章，剩下 2 章留住了；pending=5 只成 3 章，也留 2 章，失败部分不再静默丢失desuwa。

R10-B-02，[check_stock.py](/E:/code/novel-editorial/tools/check_stock.py:27)：把活跃书解析提前，默认不再统计全库，而是和 publish_stock 一致，只统计 publishing/finishing 最新一本；显式传 `--novel-id` 时仍按指定书。返回值里加了 `scope` 字段（novel / active_book / none），范围差异一眼可见desuwa。

R10-B-03，[collect_reader_stats.py](/E:/code/novel-editorial/tools/collect_reader_stats.py:143)：缺失的完读/追读率不再写 0.0，改为空字段。实测 CSV 输出 `1,,0.45` 这种形态，消费方 data_feedback 和 architect_weekly 对空值都会按缺失跳过，不再把正常章节误标低质desuwa。

R10-B-04，[get_meta.py](/E:/code/novel-editorial/tools/get_meta.py:77)：hot_topics.json 解析后先查 `isinstance(hot_data, dict)`，非对象结构回退空对象，并在 alerts.log 留痕。用 `["a","b"]` 实测不再 AttributeError 崩溃，exit 0desuwa。

R10-B-05，[release_lock.py](/E:/code/novel-editorial/tools/release_lock.py:15)：加了 `_read_owner`，兼容 preflight 写的纯文本 `PID 时间` 和 JSON `{"pid","task"}`，读入还容忍 UTF-8 BOM；释放前校验归属，活进程持有的锁拒绝并返回 1，死者 PID 按残留锁清理，任务不匹配也拒绝，并区分了 FileNotFoundError 与其它 OSError。六个场景子进程实测全过desuwa。

验证结果：compileall 五个文件全过；行为脚本 13 项断言全绿；相关测试首轮 89 passed，中间有 4 个失败是 `n8n_tmp/t.lock` 的并发测试碰撞（历史日志记过的偶发，非本次改动引入），单独重跑 test_workday 和 test_editorial_daily 共 44 passed；真实 demo.db 上 check_stock 输出 `scope: active_book`，get_meta 正常退出desuwa。

额外问题，只报不改desuno。一是 get_meta 的 sources 若本身是 dict 而非 list，`src.get("titles")` 仍会抛 AttributeError，同族崩溃没被根守卫盖住；二是 release_lock 复用了 preflight 的 `_pid_alive`，Windows 上 OpenProcess 权限不足会被当成“进程已死”，跨权限场景下仍可能误放锁；三是现役 preflight 写锁只有纯文本 PID，没有任务字段，所以 `--task` 校验要等锁写入方改成 JSON 才真正生效，PID 校验不受影响；四是消费端 data_feedback 遇到单侧缺失会整行跳过，部分有效数据也会丢掉，要做真正的按字段缺失得改消费方desuwa。

测试建议（没动测试文件）：给 publish_stock 加 pending 部分成功递减的用例，给 check_stock 加“完结书留 reviewed 章节 + 活跃书零存稿”的默认范围用例，给 collect_reader_stats 加空字段 CSV 用例，给 release_lock 加活 PID 拒绝、死 PID 清理的用例——这些都该进 tests/desuwa。
