七项都收完了mashitawa。逐个说desuwa。

R7-E-01 在 tools/publish_stock.py 第243到260行：查完作品后先算 `remaining`，一旦是 finishing 且余量 ≤0，就不再查章节、不碰发布接口，直接把小说置为 finished、余量清零、`daily_enabled=false` 并提交，返回 published=0 和「收尾余量已用完」的警告；原来循环里那行重复的余量计算也顺手删掉了desuwa。我拿 0 和 -1 两种极端数据各跑了一遍，publish_chapter 被 mock 成「一调就炸」，两次都没炸、数据库状态全部正确，tests/test_publish_stock.py 7 项也全过desuno。

R7-E-02 在 scripts/watch_daily.py 第47到49行：SUM 对空表返回 NULL，现在 `fetchone()["c"] or 0.0`，空数据打出来是 0.0 而不是 None。空 cost_logs 的实际 SQL 我也验了，原值是 None，显示值 0.0，没问题desuwa。

R7-E-03 在 novel_editorial/services/ending.py：删掉了第3行的 `from pathlib import Path` 死导入。compileall 和直接 import 都过，整个文件没有别处用 Path，删得干净mashitawa。

R7-E-04 在 README.md 目录结构那一行：`finish_rename.ps1`（已归档到 tools/archive）换成了现在 scripts 里真实存在的 `inject_fanqie_cookie.py / watch_daily.py`，跟仓库现状对上了。全文件再搜 finish_rename，零残留desuwa。

R7-E-05 两处一起处理：README.md 删掉了 `MONTHLY_BUDGET` 配置行，n8n/README.md 的成本段落改成指向数据库设置 `settings.monthly_budget` 并标注「MONTHLY_BUDGET 已弃用」。代码里活着的确实是 settings.monthly_budget（preflight、dashboard、control 都在用），README 里那句月预算表我保留了，因为它指的不是环境变量desuno。现在和 .env.example 完全一致。

R7-E-06 是重头。真正的 SystemExit 元凶有四类：desktop/release 打包副本里的 tools/archive/test_agents.py、test_skill_prompts.py（模块级 `KEY = load_key()` 直接 raise），exports/archive 下的 fix_check_stock_test.py、fix_agent_loop_test.py（模块级 raise SystemExit）。我分别在 desktop/release、exports/archive、tools/archive 各放了一个 conftest.py，用 `collect_ignore_glob = ["*test_*.py", "*_test.py"]` 把它们从自动收集里排除。中途还踩了个坑：`*test_*.py` 只能匹配 `test_` 开头的文件，`fix_agent_loop_test.py` 这种 `_test.py` 结尾的漏网，补上第二个模式才拦住mashitawa。验证结果：`pytest --collect-only -q` 不再有 SystemExit，之前是 INTERNALERROR 直接崩，现在 492 个测试正常收集desuwa。

有一处要请您定夺：tools/archive 不在任务点名的两个目录里，但它是同一份归档副本、同款导入期 SystemExit，不处理的话验证永远过不了，所以我按同类问题加了 conftest。这是清单外的一处小改动，先说明白desuno。

额外问题只报不改：全量 `python -m pytest tests -q` 是 486 过 1 挂，挂的是 test_novel_knowledge.py 的 version 断言（2 != 3），正是遗留表里 L-019 的老账，跟本轮无关；另外收集期还剩 9 个非 SystemExit 错误，n8n_tmp/douyin-api 的 8 个 ModuleNotFoundError 和 docs/research/skills/raw-zaomeng/tests 的 1 个 ImportPathMismatchError，都在 gitignore 的目录里、不在指派范围，我只记下来不动它。没有 git add/commit，工作区前几轮的其他改动也原样保留mashitawa。
