五件都收口了mashitawa，编译干净，相关测试 83 个全绿desuwa。逐项说给你听。

R9-D1-01，[record_work.py](E:/code/novel-editorial/tools/record_work.py:449) 449-472 行：成本去重键从 (run_id, node_name) 换成全字段 (run_id, node_name, model, prompt_tokens, completion_tokens)，rate 和 cost 提前算好再查重。同一个 run 里同一节点多次 LLM 调用现在全部落库，n8n 精确重放仍然幂等desuwa。我拿 20 条 costs 验过：写手A 三条、润色A 两条、审稿A 两条、再加 13 个单次节点，同一 run_id 连写两遍，落库还是 20 行，成本合计 0.2332，跟逐条按费率手算完全一致；补一条同节点新调用后变 21 行、0.24319mashitawa。旧逻辑只会留 14 行、每节点一条，这就是成本低估 50%+ 的来源desuno。

R9-D1-02，[record_work.py](E:/code/novel-editorial/tools/record_work.py:341) 341 行：seq 改用现成的 _to_int，非数字回退 0 并写 alerts.log。实测 seq="abc" 时 record_payload 照样返回 ok，坏章跳过、好章正常落库，留痕也写进去了desuwa。

R9-D1-03，[check_stock.py](E:/code/novel-editorial/tools/check_stock.py:31) 31-41 行和 [publish_stock.py](E:/code/novel-editorial/tools/publish_stock.py:262) 262-268、371、416-427 行：pending_publish 非零时当一次性目标，为零或缺失就回退 daily_chapters；daily_chapters 显式 0 就是不发，--chapters 0 也一样，publish_batch 收到 0 直接返回"本次不发布"的警告，不碰番茄desuwa。我跑了六组场景：无设置得 2、daily=0 得 0、pending=0 回退 2、pending=3 daily=2 得 3、pending=5 daily=0 得 5、pending=0 daily=0 得 0，全对；publish_stock main 在 daily=0 和 --chapters 0 下 published 都是 0，平台请求零次。有一点要说清楚：pending_publish 的 0 是系统哨兵，每次跑完就重置成 0，把它当"停发"会让日更永久停掉，所以"0=不发布"落在 daily_chapters 上，这是保住现有调度语义的唯一合理口径desuwa。

R9-D1-04，[preflight.py](E:/code/novel-editorial/tools/preflight.py:47) 47 行：load_env 改调 config._strip_inline_comment，跟 config.load_env 同源。验证：FANQIE_COOKIE=abc123 # 注释 取到 abc123，FANQIE_CSRF_TOKEN=token#fragment 完整保留 token#fragment，值内 # 不截断mashitawa。

R9-D1-05，[preflight.py](E:/code/novel-editorial/tools/preflight.py:126) 删掉顶层 LOCK_FILE 常量（原 31 行），acquire_lock/release_lock 改成必传 lock_path（126、194 行），所有调用方本来就传 {db stem}.lock。验证：常量已不存在，无参调用直接 TypeError，带路径加锁解锁都正常desuwa。

验证汇总：python -m compileall 四个文件通过；pytest 跑了 test_record_work、test_publish_stock、test_preflight_guard、test_book_isolation、test_services_regression、test_workday、test_autopilot、test_editorial_daily，52+31=83 个全过。全量没跑，因为其他代理正在并行改 core 和 editorial 的文件，现在跑会被半成品改动污染desuno。git status 确认只动了四个指派文件，没 add 没 commit，MEMORY.md 也没碰（不在指派范围；长期记忆我另记了一条angel-memory）。

测试建议，测试文件不在指派范围所以我没改：test_cost_insert_idempotent_per_run 该补"同 run 同节点多条目全落库加精确重放幂等"；record_work 加 seq="abc" 不崩且留痕；check_stock/publish_stock 加 daily=0 得 target 0、--chapters 0 不发布、publish_batch(0) 零平台调用；preflight 加行内注释和粘连 # 的 load_env 用例，再断言 LOCK_FILE 已移除。

额外发现，只报不改：upsert_chapters 对 chapters 元素没有 isinstance dict 防线，costs 循环有而它没有，混进字符串或 None 会让整段归档崩掉；全字段去重仍会合并同 run 里完全相同的两次真实调用，严格做法要 payload 指纹或唯一列，得动 schema，超本包范围；仓库里还有 docs/tmp_fix/*.err 和 ut_tests.txt 这类未跟踪残留，像是之前失败尝试的日志，按纪律我没清理desuwa。
