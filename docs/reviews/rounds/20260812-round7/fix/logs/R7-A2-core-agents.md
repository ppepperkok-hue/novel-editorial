弄好了mashitawa，四项都修完，验证也全绿desuwa。

agents.py 那边，`agent_save` 整条读写加渲染链路现在都包了异常——读失败返回 `read failed`（112 行），写失败先尝试回滚再返回 `write failed`（125-126 行），subprocess 抛 OSError 或返回码非零都走新增的 `_restore_agent_file` 回滚（147-153 行），连回滚自己失败都会拼进 error 里，不再吞掉，82 行是那个回滚帮手desuwa。

agency.py 里 `_dispatch` 改成返回 `(ok, reason)`，claim_task 的畸形 id、非正数、已被认领、行动项找不到，具体原因全带进 audit detail（claim 分支在 61-73 行，落点在 105、119、127 行）。顺手把空 body、post_issue/propose 的底层错误也补了 reason，追踪性算是齐了desuno。

seed_demo.py 在 `seed()` 开头对负数直接抛 ValueError（22 行），main 里连接数据库之前就先拦掉（71 行），CLI 退出码 1，而且不会留下空库文件——我实测过，负参连 DB 都不生成teyo。

meeting_session.py 的 `_run_locked` 查不到会话行时不再静默 return，改成抛 RuntimeError（359 行），外层兜底会标记 failed 并写 `session_failed` audit，错误里带会话 id，指错库也能一眼看出来mashitawa。

验证方面：compileall 四个文件全过；相关测试 123 个全过，全量 `tests/` 485 个全过。另外我写内联脚本把失败路径挨个打了一遍——读失败、写失败、渲染异常、returncode 非零、回滚失败、claim 被拒、负数参数、会话缺失，13 个断言全 PASS。seed CLI 负参实测退出 1 且不生成 DB。

额外发现，只报告没改：`agency.apply` 里非 dict 的 action 项只计数 rejected 不写 audit（agency.py 97-99 行）；`agent_save` 的 `path.exists()/resolve()` 仍可能抛 OSError 没兜；`_run_locked` 的 `materials is None` 分支标记 failed 但没有 audit 留痕。还有全量 pytest 收集仍会被 `desktop/release/.../archive/test_agents.py` 的 SystemExit 干扰，就是遗留表 L-015 那条。跑全量时有个插曲：`tools/editorial_daily.py` 在我运行中途被外部改动，第一次全量出现 12 个失败，重跑后全过——应该是别的会话在并行修 L-030/L-010，不是我引入的desuwa。

测试建议留给后续（测试文件不在指派范围，我没动）：agents 补 subprocess 抛错和写失败回滚的断言；agency 补 claim 被拒的 audit reason 断言；seed 补负数 ValueError 且零行写入；meeting_session 补缺失会话留痕断言。遗留表我没碰，它不在允许修改清单里，L-001、L-002、L-005、L-029 下次收口直接标已修就行。记忆我记了一条，仓库里本来就没有 MEMORY.md。
