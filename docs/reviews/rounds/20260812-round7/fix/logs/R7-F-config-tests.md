三处都收干净了mashitawa。验证先摆前面：`python -m pytest tests/test_quality_gate.py -q` 跑了 11 passed，`.env.example` 现在 48 个键全部唯一，无重复desuwa。

R7-F-01 落在 [tests/test_quality_gate.py](E:/code/novel-editorial/tests/test_quality_gate.py:55)。55-61 行新增 `test_real_ai_words_file_is_valid`，直接读 `quality_gate._WORDS_FILE` 指向的真实 ai_words.json，依次断言文件存在、可 json 解析、`ai_flavor` 是 list 且非空、每项都是非空字符串；63-67 行新增 `test_real_compliance_words_file_has_at_least_one_word`，走 `compliance.WORDS_FILE` 和 `_read_custom_words()`，断言文件存在、词表是 list 且至少含一个有效词。第 8 行 import 顺带并入了 compliance，没动别的逻辑desuwa。

R7-F-02 落在 [.env.example](E:/code/novel-editorial/.env.example:74)。74-75 行补了 `N8N_WORKFLOW_TRIGGER=每日触发`，说明标的是回退路径触发 n8n 工作流用的触发器名，默认值对着 `tools/n8n_api.py:110` 的实际消费确认过；82-83 行补了 `PYTHONW_EXE=C:/path/to/pythonw.exe`，注释写清楚它由 `desktop/main.js:15` 和 `scripts/install_daily_task.ps1:27` 读取，不设置就回退 PATH 里的 pythonw。两键都按「说明 + 默认值」补全了teyo。

R7-F-03 在 [.env.example](E:/code/novel-editorial/.env.example:20)：第 21 行的 `FANQIE_VOLUME_NAME=第一卷：默认` 整个删掉，下面的空行和注释保持不变。删除前 rg 全仓确认过，排除 `.git`、`docs/tmp_fix`、`docs/reviews` 之后零引用，其他 FANQIE 键都有真实消费方（n8n 工作流、`ending.py`、`publish_stock.py` 等），没有误伤mashitawa。

额外问题只报不改：任务书里写的审查报告路径 `docs/reviews/rounds/20260812-round7/slices/slices-summary.md` 实际不存在，真名带时间戳是 `20260812-0445-slices-summary.md`，之前几轮日志也在同一处踩坑；另外 `FANQIE_VOLUME_ID` 现在只有 `novel_editorial/services/ending.py:48-63` 在往 .env 里写，没有任何读取方，n8n 工作流也没引用，疑似下一个死配置候选——不过它有写入方，要动它得先确认面板流程不再消费，比这次这键谨慎些desuno。`docs/tmp_fix` 下还残留不少历史 .err 文件，不在我指派范围内，没碰。MEMORY.md 也没动，同样不在授权清单里desuwa。
