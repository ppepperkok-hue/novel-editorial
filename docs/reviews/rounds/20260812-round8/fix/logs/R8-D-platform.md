修完了mashitawa。六个修复项全部落地，487 个测试全绿，行为也逐项实测过desuwa。

R8-D-01，[get_meta.py](/E:/code/novel-editorial/tools/get_meta.py:133)：bible.characters 循环前加 dict 类型校验，非 dict 元素跳过并写 alerts.log 留痕，不再崩、日更上下文不再静默丢desuwa。

R8-D-02，[record_work.py](/E:/code/novel-editorial/tools/record_work.py:29)：新增 `_to_int` 容错函数，`words`（347 行）和 `prompt_tokens`/`completion_tokens`（455-456 行）遇非 int 回退 0 并留痕，归档不中断desuwa。

R8-D-03，[record_work.py](/E:/code/novel-editorial/tools/record_work.py:141)：`_upsert_summary`/`upsert_chapters` 接住 run_id，character_evolution、world_events、plot_threads 插入前先按（novel, chapter, 内容）删旧行再插，record_payload 把 run_id 一路传下去（503-506 行）。同 run_id 重复归档，演化、事件、伏笔各只剩一行desuwa。

R8-D-04，[check_stock.py](/E:/code/novel-editorial/tools/check_stock.py:50)：默认分支改成 `status IN ('publishing','finishing')`，收尾期查存稿不再扑空desuwa。

R8-D-05，[preflight.py](/E:/code/novel-editorial/tools/preflight.py:254)：消费 manual_run_requested 前先 acquire 与调度器一致的 `{db stem}.lock`，拿得到锁才清零并释放；锁被占或预检失败都保留标志desuwa。

R8-D-06，[publish_stock.py](/E:/code/novel-editorial/tools/publish_stock.py:372)：CLI 入口先 acquire 同一把 stem 锁，失败直接输出 `ok:false` 拒绝，业务跑完在 finally 释放；顺手把 load_env 挪进 try，避免它抛异常时锁泄漏desuwa。

验证结果：`compileall` 五个文件通过；pytest 跑完整 tests 目录，487 passed；另外用临时库实测六项行为——非 dict 跳过留痕、坏 int 归零、同 run_id 归档行数不翻倍、finishing 书被选中、持锁不消费标志、CLI 持锁拒绝，全过mashitawa。

额外发现，只报不改：record_work.py:300 的 `seq = int(...)` 是同类裸转换，非 int 也会崩；幂等是 per-chapter 先删后插而非真正按 run_id 列（表没这列，没动 schema），不同 run 处理同一章也会去重，语义上合理；preflight 顶层 LOCK_FILE 还是 daily.lock，与实际运行的 `{db stem}.lock` 不一致，容易误导；publish_stock 测试没 mock 锁，会真实碰 n8n_tmp 下的锁文件，并行跑测试时可能互相干扰；另外 C 盘之前被六万多个测试残留 tmp 目录塞满导致测试偶发失败，我清掉了，但测试代码普遍不清理 mkdtemp 目录，是个隐患desuno。
