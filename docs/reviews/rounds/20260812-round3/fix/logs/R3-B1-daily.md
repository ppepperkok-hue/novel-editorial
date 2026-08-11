修完了mashitawa。五处都动了，compileall 三份文件全绿，六份相关测试跑了 81 通过、2 失败——失败的两条正是 test_workday 里旧断言在坚持「dry-run 收工也要写库」，那是本轮要修掉的行为本身，测试文件不在指派范围，我没动它。

先说 workday 那件。dry-run 下所有状态机持久化写都收口了：_morning_plan 的 plan/phase、open 的 producing/skipped/awaiting_close、resume 的 producing/awaiting_close、_close_locked 的 closing/collab_summary/finished 和 closed 审计，全用 if not dry_run 包住（tools/workday.py 96、166-182、217-224、254-323）。我专门验证过：dry-run close/resume 之后 daily_runs 那行仍停在 awaiting_close，audit_logs 里没有 closed，真实运行路径的持久化行为没变desuwa。

重做那件，把全局布尔换成了按 run 的幂等键集合，键优先级是 action_id > message_id > body（editorial_daily.py 238、1092-1104、1200-1211），第二个重做请求现在也会走 _review_retry 并结算，不会再悬置。_settle_rework 检查 mailroom.resolve 和 activity.update_action 的返回值，失败写 settle_rework_failed 审计（1227-1257）；outbox 里行动项创建失败也会警告、仍按重做执行（115-153）。我拿两条重做请求同时进链路试过，两个 action 都 done、两条消息都 resolved，这手不亏desuwa。

发布链和 mailroom 各是一件。cover_article 响应现在必须 code==0，否则进失败分支、记 failed_nodes/errors，绝不再碰 publish_article（1298-1324），用 fake 响应验证过会停链。主编分派广播（634-646）和重写轮的两处 mailroom.send（1017-1029、1045-1057）都检查返回值，失败进 ctx.warnings，不静默吞了mashitawa。

relations 那件，decay 的 days 参数真正用上了，按 0.95^(days/7) 和 0.90^(days/7) 衰减，默认 days=7 与原来完全一致，数值仍 clamp 在 0-1（tools/relations.py 85-105）。tools/promises.py:130 本来就传 days 进来，不需要改，我确认过desuwa。

额外发现只报告不改：editorial_daily.py:543 的 _preflight 在 dry-run 下仍写 audit_logs，和「dry-run 无副作用」的口径不一致；test_workday.py 那两条测试（102-123、125-146）建议改成断言 dry-run 后行状态不变，等测试文件开放了再补。MEMORY.md 不在指派范围，我没碰；其余限制就是那两条旧测试等更新teyo。
