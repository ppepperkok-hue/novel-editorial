修完了mashitawa，四个指派文件只动了该动的行，别的文件一个没碰desuwa。git add/commit 没做，MEMORY.md 也没动。动手前我先按 systematic-debugging 的规矩，用一次性脚本（不落盘）把四处症状各自复现了一遍，确认根因才下的patchteyo。

R3-A2-01，[monitor.py](E:/code/novel-editorial/novel_editorial/monitor.py:36) 的 `run_checks` 改成无条件合并 `_load_n8n_env()`，显式 env 优先、.env 补缺，和 config.load_env 的语义一致。复现里只有 FANQIE_COOKIE、.env 里补着 CSRF 时，之前照样误报缺失，现在 `issues=[]` 了desuwa。

R3-A2-02，[scheduler.py](E:/code/novel-editorial/novel_editorial/scheduler.py:47) 补了 datetime 导入，`tick` 未注入时钟时落到 `datetime.now()`，date 字段输出 `YYYY-MM-DD` 真日期。复现时从字符串 `"None"` 变成了 `"2026-08-12"` masuwa。

R3-A2-03，[seed_demo.py](E:/code/novel-editorial/novel_editorial/seed_demo.py:21) 把 published 和 reviewed 依次 clamp 到 chapters 之内，draft 永远非负、总章数不越界。复现 chapters=3、published=2、reviewed=2，之前生成 4 章状态错位，现在正好 3 章，状态是 published、published、reviewed teyo。

R3-A2-04，[web_api.py](E:/code/novel-editorial/novel_editorial/web_api.py:646) 两处都改了。Content-Length 解析失败或为负，现在返回 400 的结构化 JSON `invalid Content-Length`，不再 500；`/api/agent_actions/create` 的 session_id/meeting_id 先做整数清洗，非数字返回 400 并带错误信息，返回前把 conn 关掉不泄漏。数字字符串 "3"/"5" 照常 200 建单，复现脚本里全验证过了mashitawa。

验证结果：`python -m compileall` 四个文件通过；pytest 跑了 test_monitor、test_scheduler、test_seed_demo、test_web_api、test_hardening、test_review_v3、test_review_v4，52 passed。测试文件不在指派范围，我没改，补测试的建议给你留着：monitor 补单平台凭据加 .env 场景，scheduler 断言 date 匹配 `%Y-%m-%d`，seed_demo 补 published+reviewed 超限的 clamp，web_api 补垃圾 Content-Length 返 400、session_id 非数字返 400、数字字符串返 200。

额外问题只报告不动手desuwa：do_POST 对非法 JSON body 本身仍会 500，跟 Content-Length 是同一类输入问题；create 的 novel_id 没做整数清洗，非数字会以字符串写进 agent_actions 和 agent_activity（SQLite 不报错但数据会脏）；seed_demo 对负数参数没有校验。另外工作区里 services 下五个文件（agency、agents、control、knowledge、misc）本来就有未指派的改动，不是我弄的，我也没去清理teyo。
