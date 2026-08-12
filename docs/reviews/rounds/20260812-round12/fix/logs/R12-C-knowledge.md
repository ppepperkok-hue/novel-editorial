弄好了mashitawa，R12-C 七项全部修完，验证也跑透了desuwa。

先讲两个并发的重头。novel_knowledge.py 的 upsert_ex 更新路径（tools/novel_knowledge.py:247-297）现在走原子循环：history 用 `INSERT OR IGNORE ... WHERE NOT EXISTS` 在事务里防重，行更新加 `WHERE version=?` 乐观锁，撞锁就重读重试，五次耗尽才显式报错desuwa。另外在 tools/novel_knowledge.py:37-50 加了唯一索引守护（knowledge_id+version），老库里已有重复行时自动跳过建索引，不破坏历史数据desuno。双线程实测 20 轮不同内容并发写：最终 version=3、history 的 v1/v2 各一条、零重复；10 轮同内容并发保持 version=1、history 零条；带遗留重复行的旧库也能正常更新且不新增重复mashitawa。

clean_novel_knowledge.py 两处。链式相似规则（tools/clean_novel_knowledge.py:122-205）改用并查集聚类，A~B~C 这种链只保留版本最高的一行、其余全部并入它，计划里不再出现「上一轮的 keep 被当 drop 删掉」的链desuwa。实测三行规则合并后一行保留、三段内容一句没丢。无 item 对应的 power/金手指（tools/clean_novel_knowledge.py:108-118、313-322）不再删，计划带 keep_as 字段后执行时把 category 改成 item 原地保留；手写旧格式计划（没有 keep_as）仍按显式删除处理，兼容老调用方desuno。

distill_lessons.py 的 _meeting_material（tools/distill_lessons.py:85-122、136-163）给 transcript/report 补了类型校验，非 dict/list 一律回退空结构，并把 warnings 一路带进 activity 和返回结果（tools/distill_lessons.py:203、302、311）。实测 transcript 是 dict、report 是 list 时不再崩，正常蒸馏且 warnings 清楚留痕mashitawa。

剩下三个小的。长内容合并判定（tools/novel_knowledge.py:219-222）改为现查库用完整 content 比较；我构造了「截断 120 字符相似度 0.417、完整内容 0.65」的用例，旧逻辑会漏、现在正确并入。knowledge_keeper 对非 market 文件（tools/knowledge_keeper.py:235-253）每次跳过都写一条 keeper_auto_update_skipped_non_market 审计，并在 keeper_run、activity、返回结果里汇总（327、341、351 行）desuwa。export_agent_prompts 的 proxy 模式（tools/export_agent_prompts.py:73、122、126）改为返回 0、`SystemExit(main())`，docstring 也写明「不支持但正常、不是失败」，实测 CLI 退出码 0mashitawa。

验证：五个文件 compileall 全过；定向 pytest（novel_knowledge/clean_knowledge/distill/knowledge_keeper/review_v3）30 个用例全绿。全量 run_tests.py 504 个里 5 个失败，我复跑过了：3 个是并行环境的锁竞争（bad.lock 残留，复跑已过），2 个稳定失败——test_meeting_dry_run_full_chain 和 test_review_tone_follows_friction——分别在 agent_meeting.py 和 editorial_daily.py 上，正是 R12-A2/B 其他分片正在修的审查项，不在本包文件里desuno。

额外问题只报不改：export_agent_prompts 非 proxy 路径全节点缺失仍会 exit 0（R11 遗留）；distill_lessons 元素缺 title/content 仍静默 continue（R11 遗留）；旧库已有重复 history 行的数据本身没清理，靠事务检查兜底desuwa。测试建议也列一下：novel_knowledge 补并发双线程和长内容合并用例，clean_knowledge 补链式三规则与无 item 保留用例，distill 补非法类型回退断言，knowledge_keeper 补非 market 审计断言，review_v3 补 CLI 退出码 0 断言——测试文件不在指派范围，我一个没动teyo。MEMORY.md 也没更新，工作区里其他分片的修改我碰都没碰desuwa。
