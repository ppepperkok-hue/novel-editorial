五个修复项全部落地了mashitawa。编译干净，五个相关测试文件 33 个用例全过，我只动了指派的那四个文件desuwa。

R4-C-01，`tools/clean_novel_knowledge.py:230-258`。`apply_clean` 的 rename 和 state_rows 两条路径，在 `merge_into` 为空时不再直接 UPDATE，而是先现查一次目标规范名是否已被同一轮前面的 rename 占用，占用就走 `_merge_history` 合并。复现时的三行 `cultivation-level:*` 收敛场景，从 IntegrityError 变成一行 `cultivation-leve`，三份内容完整拼接，version 3、history 留痕 2 条；审查点名的「沈叙·A / 沈叙·B」无基础行场景也合并成了「沈叙」，内容 `state-A\n\nstate-B` 一点没丢desuwa。

R4-C-02，`tools/novel_knowledge.py:417/440/448` 加 `465-467`。`sync_from_chapters` 的三处 `upsert` 换成 `_upsert_if_changed`，并给这个辅助函数补了 `change_note` 参数；内容没变就直接跳过，不再把「第N章」当变更塞进 history。连续同步三次，第一次 count 2，后两次 count 0，version 钉在 1、history 零新增desuwa。这样改不动 `upsert_ex` 的全局语义，带 change_note 的合并审计行为原样保留，现有测试一个不破desuno。

R4-C-03，`tools/clean_novel_knowledge.py:188-227`。`_merge_history` 现在读被合并行的 content 和 entity，内容不同就以段落形式拼进 keep 行，合并前的旧内容写进 history，change_note 记 `merged:实体名`。验证里「阴阳守恒」和「阴阳守恒之律」内容不同，合并后 keep 是 `rule-1\n\nrule-2-different`，历史里能看到 merge 记录，不再静默丢弃desuwa。有个边界要说明：keep 行已被前面计划删除的 guard 分支，现有测试 `test_merge_history_keeps_missing_drop_safe` 锁死了删除行为，我按测试契约保留了，没动teyo。

R4-C-04，`tools/knowledge_keeper.py:166-169`。auto_updates 应用前先比对模型返回的 body 和现有内容，逐字相同就直接 continue，不重写、不刷新 updated_at、也不写 keeper_auto_update 审计。实测同一 body 跑两次，updated_at 停在 2026-08-10，审计零条desuwa。

R4-C-05，`tools/export_agent_prompts.py:60-82`。model、temperature、max_tokens 的 `find()` 全部加了 -1 保护，缺字段或引号不闭合就打印 skip 并跳过该节点，绝不写坏文件；max_tokens 没有尾逗号时截到行尾。四个畸形样例（无 model、无 temperature、model 引号不闭合、无 system 段）全部跳过且不落盘，合法样例正常导出 writer.md，frontmatter 是 model: gpt-4 / temperature: 0.7 / max_tokens: 2000desuwa。

验证汇总：`python -m compileall` 四个文件全过；pytest 覆盖 `test_clean_knowledge`、`test_novel_knowledge`、`test_knowledge_bible`、`test_knowledge_keeper`、`test_review_v3`，33 个用例全绿。工作区里其他修改文件是其他分片的活，我这边只有四个指派文件有改动，MEMORY.md 没动desuwa。

额外发现，只报告不修：`export_agent_prompts.py` 的 END_MARK 如果恰好出现在 system 正文内部，正文会被提前截断，这是格式识别问题不是 -1 崩溃；`_merge_history` 的 keep 缺失分支仍会删掉 drop 行及其 history，被现有测试锁死，链式计划极端情况下还有丢内容的风险；`upsert_ex` 对 content 相同但 change_note 非空的调用仍会 version+1，其他调用方如果带 note 重复写还会有 churn，这次只堵了章节同步的口子；另外该文件顶部 `import re` 是历史遗留的未用导入desuno。

测试建议也列一下：给 `apply_clean` 补多实体收敛且无规范名行的用例（用审查里的 cultivation-level 三行）；给 `sync_from_chapters` 补重复同步三次 version/history 不变的用例；给 `_merge_history` 补不同内容合并保留的用例；给 `knowledge_keeper` 补相同 body 不重写不刷时间的用例；给 `export_agent_prompts` 补非代理畸形 jsonBody 跳过且不落盘的用例。这些都在指派范围外，我没动测试文件，等分片评估后由负责方落进去teyo。
