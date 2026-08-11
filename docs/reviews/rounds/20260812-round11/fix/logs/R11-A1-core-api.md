弄好了mashitawa。四项里三项是真改，pipeline 那项查完发现动不得desuwa。

先说 R11-A1-01。meeting_session.py 第 19 行加了专用的 `_CREATE_SESSION_LOCK`，第 36 行起把「检查 active + INSERT + commit」整个包进锁里desuwa。我没用现成的 `_MEETING_LOCK`——那把锁被 run_session 攥着开完全程，最长一个钟头，拿它锁创建会把 API 请求活活卡死，所以单独开了一把teyo。验证是照审查报告的复现方式跑的：120 个线程同时 create_session，结果只有一个成功、库里只有一条 running，竞态确实没了desuwa。

R11-A1-02，pipeline.py 有引用，删不了desuwa。`novel_editorial/novel_flow.py:14` 直接 `from novel_editorial import db, pipeline, planner`，第 33 行还在调 `pipeline.generate_one_chapter`；`tests/test_hardening.py:8` 和 `tests/test_pipeline_generate.py:8` 也直接 import 了它，`autopilot.py` 又挂 novel_flow，一串旧链路都还活着。所以按「有引用则说明」，文件保持原样，我没有动它mashitawa。

R11-A1-03，web_api.py 的 `/api/knowledge_drafts` accept 分支，`write_knowledge` 现在被 try/except ValueError 包住（972~978 行一带），出错返回 400，跟 save 分支一致desuwa。HTTP 实测：草稿标题带换行触发校验错误，返回 400，草稿状态还留在 draft，没有被误标成 accepted，这手不亏desuwa。

R11-A1-04，三个分支全部套上 try/finally 关连接：`/api/knowledge`（896~930）、`/api/knowledge_drafts`（932~1001）、`/api/novel_knowledge`（1003~1049）desuwa。我用包装连接计数实测：六个请求加上启动和快照线程的连接，开了 9 条、关了 9 条，零泄漏mashitawa。

验证汇总：compileall 三个文件全过；相关测试 81 个全绿；全量 497 个测试里 496 过、1 个挂——挂的是 test_ai_taste_check 的四字排比用例，问题在 tools/ai_taste_check.py，那个文件不是我改的，本来就在工作区里带着别人的改动，跟本轮无关desuwa。

测试建议留给下一轮：给 create_session 加并发用例（多线程各自连接，断言仅一个成功且 running 只有一条）；给 accept 分支加 HTTP 用例断言 ValueError 返回 400 且草稿保持 draft；给三个知识端点加连接计数用例防泄漏回归teyo。

额外问题只报不改。一是 tools/agent_meeting.py:626-639 的 CLI 路径会直接 INSERT running 会话，不经过 create_session 也不受这把锁管，misc.start_topic_meeting 和定时周会都走它，跟 web_api 并发时仍可能造出两个 running，建议下一轮把创建收敛到同一个入口desuwa。二是 `/api/novel_knowledge` 的 upsert 捕获 ValueError 后返回 200 + ok:false，跟 save/accept 的 400 语义不一致，也算个尾巴desuwa。MEMORY.md 不在指派范围，我没动mashitawa。
