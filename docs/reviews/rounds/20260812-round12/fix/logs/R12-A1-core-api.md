修好了mashitawa。两项都在指派文件里，别的一律没碰desuwa。

R12-A1-01，[daily_runs.py](E:\code\novel-editorial\tools\daily_runs.py:109) 的 sync_from_n8n，存在性检查从循环开头挪到执行数据算完以后，已导入的行不再 continue 跳过，而是走 [第 128 行](E:\code\novel-editorial\tools\daily_runs.py:128) 的 UPDATE，把 status、started_at、finished_at、failed_nodes、error、published、updated_at 全部按最新 n8n 数据刷新desuwa。written 仍然只算新增插入，第二次同步返回 0，幂等语义没变desuno。compileall 通过，test_daily_runs 六个用例全绿；手工复现也过了，先以 running 导入，n8n 改成 success 再同步，状态变 success、结束时间从空更新成 13:32:12，再从 failed 改回 success，失败节点和错误信息也一并清掉了mashitawa。

R12-A1-02，[web_api.py](E:\code\novel-editorial\novel_editorial\web_api.py:1029) 的 /api/novel_knowledge upsert 分支，ValueError 捕获后补了 http_status = 400，跟 save（919 行）、accept（978 行）同一套语义了desuwa。实测非法 category 返回 400 + ok:false + 错误信息，正常 upsert 仍是 200 ok:true；test_web_api 二十个用例全绿，flow_graph 四个也过了mashitawa。

额外问题只报不改desuwa。upsert 的 entity 和 content 都为空时，接口仍返回 200 + ok:false 且没有 error 字段，既然本轮统一错误语义，这块要不要也收成 400，请您定夺desuno。更新路径对每个已失败的运行每次同步都会重调 _execution_failure，n8n API 临时不可用时会把已存好的失败详情覆盖成「获取失败详情出错」，本地轮询下还有重复 API 调用desuwa。INSERT 分支不写 updated_at 而 UPDATE 分支写，新旧 n8n-legacy 行状态有点混，小事desuwa。另外任务书里的 slices-summary.md 路径又漂了，真实文件是带时间戳的 20260812-0753-slices-summary.mddesuno。测试建议：test_daily_runs 补「running 导入→success 再同步」用例，断言状态和 finished_at 被更新、第二次 written 为 0；test_web_api 补非法 category 返回 400 的用例desuwa。仓库没有 MEMORY.md，本轮未更新mashitawa。
