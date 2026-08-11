弄好了mashitawa。四个修复项全部落地，我只动了指派的那四个文件，工作区里其他 agent 的改动一概没碰desuwa。

R5-F-01 在 quality_gate.py 的第 10、22-34 行：加了 `import warnings`，加载 ai_flavor 时先做 isinstance 校验，非 list 就告警并回退内置词表，不再按字符拼正则。我模拟过 `ai_flavor` 为字符串的场景，警告正常弹出，密度保持 0.0，词表仍是内置那份desuwa。

R5-F-02 在 compliance.py 的第 23-25、65-83、86-101、104-115 行：新增 READ_WORDS_WARNING，`_read_custom_words` 捕获 `(OSError, UnicodeDecodeError)` 后告警并返回 None；`check` 里区分了缺失、读取失败、空/全注释三种分支，`_load_words` 用哨兵参数接收已读词表，不会重复读文件重复告警。坏编码词库的临时文件实测只出一条读取失败警告，扫描用内置词继续、不崩溃mashitawa。

R5-F-03 在 tests/test_compliance.py 的第 13-18、31-86 行：补了缺失、空、全注释三组 warnings 断言，还加了坏编码回退测试和真实 compliance_words.txt 的可读守护，同时强化了自定义词合并用例，断言无任何 warnings。验证命令 `python -m compileall` 通过，`python -m pytest tests/test_compliance.py -q` 是 8 passed，连带 quality_gate、editorial_daily、review_retry、hardening 一起跑，54 个用例全绿desuwa。

R5-F-04 在 .env.example 的第 27、33 行：补上 `REVIEW_RETRY_MAX=1`（config.py:59 与 editorial_daily.py:994 消费）和 `MEETING_HEARTBEAT_TIMEOUT_MINUTES=60`（meeting_session.py:87 消费）；`MONTHLY_BUDGET`、`N8N_PASSWORD`、`N8N_HOST`、`N8N_LISTEN_ADDRESS` 四个死键全部移除，`N8N_EMAIL`/`N8N_TMP_PW` 保留——n8n_api.py 实际只读这两个desuwa。

额外发现，只报告不改：README.md:160 和 n8n/README.md:53 还在把 `MONTHLY_BUDGET` 当配置键写，现在示例文件已移除，文档对不上teyo；另外 compliance_words.txt 至今全注释，真实路径每次发布扫描都会带 EMPTY 警告，直到真正填词才会消停；quality_gate 对 ai_words.json 缺失或 JSON 损坏仍是静默忽略，只有非 list 会告警，和 compliance 的容错不对称。MEMORY.md 不在指派范围，没有动desuwa。
