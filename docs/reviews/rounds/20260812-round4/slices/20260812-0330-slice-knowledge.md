审查范围：prompts/ 与 6 个 knowledge 相关工具。基线：python -m compileall 全部通过；slice 相关 36 个 unittest 全部通过；--snapshot/--dry-run/--sync/--meeting-id 等只读 CLI 均正常退出。但存在两个可复现的 P1：clean_novel_knowledge --apply 在常见历史脏数据（多实体收敛同名）下必然抛 UNIQUE 约束崩溃，以及 sync_from_chapters 对未变化内容仍无限 version+1/history 膨胀（P1-5 幂等修复未覆盖章节同步路径）；另有 P2 的 merge 内容静默丢失与两个 P3，因此该补丁不能视为正确。

Full review comments:

- [P1] clean_novel_knowledge --apply 在多个实体收敛到同一规范名时崩溃 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:203-211
  tools/clean_novel_knowledge.py:203-211 的 apply_clean 对 rename/state_rows 计划逐行执行 `UPDATE novel_knowledge SET entity=?`，而冲突检测只在规划阶段（_plan_renames:35-61 / _plan_state_rows:63-87）做了一次静态查询：当 ≥2 个脏实体 normalize 后同名且规范名行不存在时，每个计划项的 merge_into 都是 None，apply 时第二个 UPDATE 即触发 `sqlite3.IntegrityError: UNIQUE constraint failed: novel_knowledge.novel_id, novel_knowledge.category, novel_knowledge.entity`，整个 --apply 中断。已复现：插入三行 entity 分别为 `cultivation-level:foundation`、`cultivation-level:qi-refining`、`cultivation-level:qi-refining-peak`（normalize 后均为 `cultivation-leve`，MAX_ENTITY_LEN=16 截断），plan 显示三行 merge_into 均为 None，apply_clean 在第 208 行抛 IntegrityError。真实触发场景就是本工具的目标数据——历史遗留的「角色·状态」多行（如「沈叙·A」「沈叙·B」且无「沈叙」基础行）或两个括号注释实体；现有测试 test_plan_merges_state_rows 只覆盖了规范名行已存在的情形，未覆盖此崩溃路径。

- [P1] sync_from_chapters 重复同步仍无限 version+1 并膨胀 history 表 — E:\code\novel-editorial\tools\novel_knowledge.py:196-200
  tools/novel_knowledge.py:196 的幂等短路 `if row["content"] == content and not change_note` 只覆盖无 change_note 的调用，而 sync_from_chapters（novel_knowledge.py:419/442/450）每次都传 `change_note=f"第{seq}章"` 等非空值，因此即使内容完全未变也会走历史记录分支：INSERT novel_knowledge_history + version=version+1。已复现：对同一 chapter_summary 连续调用 sync_from_chapters 3 次，character/plot/timeline 三个实体 version 从 1 涨到 3，history 新增 6 行且内容重复；demo.db 中 item/金手指 version=7、history 12 条（其中 6 条同内容 version=1）即为长期 churn 的实证。每日 --sync-latest 定时任务持续触发，导致 history 表无限膨胀、version 失真（不再反映真实内容变更次数）、审计噪声，且 commit f4c7361（P1-5 idempotent upsert 修复）对章节同步路径实际无效。

- [P2] _merge_history 静默丢弃被合并行的 content，相似但内容不同的设定丢失 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:184-200
  tools/clean_novel_knowledge.py:184-200 的 _merge_history 只做两件事：把 drop 行的 novel_knowledge_history 记录改挂到 keep 行，然后 DELETE drop 行；drop 行的 content 字段从未被合并或保留。_plan_similar_rules（:115-143）的相似判定只基于 entity 字符串（ratio>=0.7 或 prefix>=6 且 ratio>=0.55），不比较 content，因此「阴阳守恒」与「阴阳守恒之律」这类 entity 相似但描述不同规则的 world_rule 行，apply 后后者内容被无条件删除；链式计划（如 keep 行先被前一条计划删除）走 guard 分支时更是连 history 转移都没有，直接 DELETE。现有测试 test_plan_merges_similar_rules 用相同 content（"规则一"）构造数据，恰好掩盖了内容丢失。该工具默认 dry-run 且 apply 前有备份，但一次 --apply 即静默损失设定内容，无任何提示。

- [P3] knowledge_keeper 自动更新无内容变化检测，每次运行都重写知识包并刷新 updated_at — E:\code\novel-editorial\tools\knowledge_keeper.py:158-183
  tools/knowledge_keeper.py:158-183 的 auto_updates 应用段只检查 `file not in market_files or not body`，未与现有 body 比对；即使模型返回的 body 与 prompts/knowledge 下当前内容逐字相同，也会调用 write_knowledge 重写文件、把 updated_at 刷新为当前时间并写 keeper_auto_update 审计。知识管家为定时任务，每次运行都会对全部 market 包产生无意义写盘与 updated_at 失真（内容未变却显示为刚更新），并污染审计时间线。

- [P3] export_agent_prompts 非代理导出路径对 find() 无 -1 保护，格式不符时静默写坏文件 — E:\code\novel-editorial\tools\export_agent_prompts.py:60-73
  tools/export_agent_prompts.py:60-73 中 `sm = body.find("model:'")`、`body.find(",", tm)` 等均无 -1 检查：若 jsonBody 改用双引号或字段顺序变化，sm=-1 时 `body[-7:...]` 会从文件尾部截取垃圾片段作为 model/temperature，并继续写盘；END_MARK 若在 system 文本中出现也会提前截断。当前仓库 n8n/novel_workflow.json 为 PROXY_MODE（脚本直接 return），该路径是死代码不会触发，但工作流一旦切回非代理模式且格式有出入，会静默生成损坏的 prompts/agents/*.md 而没有任何失败提示。
