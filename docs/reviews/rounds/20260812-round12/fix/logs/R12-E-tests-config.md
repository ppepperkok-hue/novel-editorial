三项修复都做完了，验证也跑了两轮desuwa。先说结论：我负责的测试全绿，全量套件里那 2 个红不是我的手笔。

第一项，[.env.example](E:/code/novel-editorial/.env.example:85) 第 85–86 行补上了 NOVEL_DATA_DIR 的说明，写明它决定 n8n_tmp、exports、demo_data、alerts.log 这些运行时落盘位置，不设置默认仓库根目录，只读安装要指到可写目录，桌面版会自动注入mashitawa。

第二项，[run_tests.py](E:/code/novel-editorial/run_tests.py:12) 第 12 行起加了 EnvConfigContractTests 契约守护，第 138 行挂进套件。它解析 .env.example 全部 48 个键，20 个在 config.py 里直接消费（用 AST 读源码，不是猜），28 个在 config.py 之外消费，我建了一张键→消费文件的注册表并逐个验证引用还在；config 默认值也和示例逐一比对过，目前零漂移desuwa。

第三项，[tests/test_apply_architect.py](E:/code/novel-editorial/tests/test_apply_architect.py:28) 新建，5 个直接单元测试：merge_blueprints 对 None/空输入和非数字 seq 的容错、按 seq 合并排序，以及 apply_report 蓝图落盘和角色演变两路的重复应用幂等desuwa。

验证结果：`python -m pytest tests/test_apply_architect.py -q` 5 passed；`python run_tests.py` 跑出 504 个测试，我的 7 个（5 个新单测加 2 个契约测试）全过，但整体 2 个失败。我单独重跑并核对了 diff，这两个都是别的修复包改到一半留下的：agent_meeting 的 dry-run 已经改成不落库，而 test_agent_meeting 还在断言 weekly_meetings 应该有 1 行；_review_tone 查询方向修好了，test_editorial_daily 插入的关系方向却没跟着换。两个文件都不在我被允许修改的清单里，我只报告不动手teyo。

另外还发现一个值得记下的边界缺陷：merge_blueprints 对没有数字 seq 的 updates 永远追加新条目，同一份无 seq 更新重复应用会不断新增蓝图，幂等只对带 seq 的更新成立。我的幂等测试特意用的有 seq 数据，这个缺陷建议下轮修（给无 seq 更新做内容去重或归属到已有条目）masuwa。

其余 4 个模块的测试建议：architect_weekly 补 build_materials 的上下文完整性断言，write_diaries 补 write 的 dry-run 不落盘语义，app_settings 补读改写与边界值，meeting_kinds 补各会议 kind 的 payload 结构。这些目前都只有间接覆盖desuwa。项目 MEMORY.md 我没有动，本轮改动只限指派的三处mashitawa。
