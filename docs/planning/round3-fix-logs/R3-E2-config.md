弄好了mashitawa。三处修复都收在指派范围内，`compliance_words.txt` 保持原样，git 没有 add 也没有 commit，其他文件一概没碰teyo。

R3-E2-01，[.env.example](E:/code/novel-editorial/.env.example:72) 里成本单价的重复键合并了desuwa。原来 34-35 行一组、58-59 行一组，setdefault 先值生效，后一组用户改了也白改。现在只保留 72-74 行这一组，注释写明「本组为唯一生效定义（旧重复项已合并）」，被删那组的 pro/flash 单价说明也并了过来，默认值和注释一条没丢teyo。

R3-E2-02，文档补齐mashitawa。`MEETING_MODE` 补在第 34 行，标注 rounds|open 两种取值和失败回退语义；`AGENT_CTX_MESSAGES/MEMORIES/RELATIONS/PROMISES/ACTIONS/TRUNCATE` 六条在 36-42 行，用途和默认值都按 [config.py](E:/code/novel-editorial/novel_editorial/config.py:50) 的实际定义写的；`N8N_BASE` 和 `N8N_WORKFLOW_DAILY/WEEKLY/KEEPER` 在 52-58 行——这几个键代码里明明在读，.env.example 之前却压根没有，属于漏写desuwa。`N8N_EMAIL`、`N8N_PASSWORD`、`N8N_TMP_PW` 也补了逐键说明。

R3-E2-03，[compliance.py](E:/code/novel-editorial/novel_editorial/compliance.py:62) 不再静默用空词库了teyo。词库读取抽成 `_read_custom_words()`，`check()` 在文件不存在或空/全注释时，返回结构新增 `warnings` 列表如实报告，同时抛 RuntimeWarning 提醒（86-104 行）。`compliance_words.txt` 我没动——它现在确实只有注释，所以每次扫描都会先响一声，而不是假装有自定义词desuwa。

验证结果：`python -m compileall novel_editorial/compliance.py` 通过；`tests/test_compliance.py` 3 个用例全过；`test_editorial_daily.py` 和 `test_review_retry.py` 里 compliance 相关 2 个用例全过，而且新警告真的在测试输出里打出来了；.env.example 扫了一遍，49 个键全部唯一，无重复，注释渲染和原有风格一致mashitawa。另用临时词库模拟了缺失、全注释、有自定义词三种情况，告警行为分别是警告/警告/无警告，符合预期desuwa。

额外问题，只报告不改。`N8N_PASSWORD` 在仓库代码里没有任何读取方，`tools/n8n_api.py` 实际用的是 `N8N_TMP_PW`，这键现在是死配置；`N8N_HOST` 和 `N8N_LISTEN_ADDRESS` 同样没有代码消费，只剩文档价值；`REVIEW_RETRY_MAX` 在 config.py 和 editorial_daily 里都在用，.env.example 却漏了这条，和本次文档缺口同类。测试建议写在结果里：在 `tests/test_compliance.py` 补三组用例——词库缺失、空/全注释、有自定义词，分别断言 `warnings` 非空、非空、为空，这个文件不在指派范围所以没写teyo。最后，审查 F6 提到的 `docs/reviews/*.err` 和根目录 `_repro_*.py` 误提交风险仍在，git status 里它们都还是未跟踪状态，收尾时记得清。MEMORY.md 没动，也不在本次范围desuwa。
