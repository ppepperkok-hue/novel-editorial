审查范围：prompts/（agents+knowledge）与 6 个工具（novel_knowledge / knowledge_keeper / distill_lessons / clean_novel_knowledge / ai_taste_check / export_agent_prompts），依赖契约仅核对 db.py、config.py、llm_client.py、services/{knowledge,audit,activity}.py。基线：compileall 全部通过，slice 定向测试 16 passed（test_novel_knowledge + test_clean_knowledge），demo.db 上 graph/snapshot/resolve/sync_latest 冒烟正常且顺序同步幂等，export_agent_prompts 确认 proxy 模式不写文件。结论：代码整体可运行、顺序路径幂等，但存在 2 个 P1——upsert_ex 并发读-改-写竞态导致 history 重复（demo.db 金手指 v1-v6 各两条重复为实证），以及 clean 工具链式相似规则合并静默丢失整行内容（已复现）；另有 1 个 P2（无 item 的金手指被删）与 4 个 P3，均需修复后才视为正确。

Full review comments:

- [P1] upsert_ex 并发更新时重复写入 history，审计链被污染 — E:\code\novel-editorial\tools\novel_knowledge.py:230-237
  tools/novel_knowledge.py:230-236 的更新路径是「SELECT 旧值(186-190) → INSERT history → UPDATE version+1」，中间没有事务隔离。两个写者（scheduler 每日同步 + web_api 手动 upsert/CLI）并发时都会读到相同的旧 (version, content)，各写一条相同 version 的 history，最终 version 只 +1 但 history 出现重复。已用双进程并发复现：同一行 6 次并发 upsert 后 version=5，history 中 version 1 出现 2 条。demo.db 中 knowledge_id=11（金手指）存在 v1-v6 各两条完全相同的 history（created_at 同秒），证实该竞态在实际运行中反复触发。修复方向：读-改-写包进 `BEGIN IMMEDIATE` 事务，或给 novel_knowledge_history 加 UNIQUE(knowledge_id, version)。

- [P1] clean_novel_knowledge 链式相似规则合并时静默丢失整行内容 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:194-201
  tools/clean_novel_knowledge.py:194-201：`_merge_history` 在 keep 行已被前面的合并删除时（keep is None），直接 DELETE drop 行及其 history，内容不进任何保留行。`_plan_similar_rules`(131-146) 按 entity 顺序两两生成计划且不做依赖分析，当出现 A~B、B~C 均相似且 version 满足 A.v > B.v >= C.v 时（B 在 (A,B) 中是 drop、在 (B,C) 中是 keep），apply 顺序执行后 C 的内容被永久丢弃。已复现：插入「灵气复苏 v5 / 灵气复苏规则 v3 / 灵气复苏规则详解 v1」后 --apply，最终只剩 A（内容=A+B），C 的内容「另有灵脉分布与宗门传承」既不在行里也不在 history 里。现有测试只覆盖单一 pair，未覆盖链式场景。建议计划阶段排除已作为 drop 的行，或 None 分支把 drop 内容合并到链上最终的 keep。

- [P2] clean_novel_knowledge 删除无 item 对应的 power/金手指，唯一设定记录丢失 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:266-274
  tools/clean_novel_knowledge.py:266-274：`_plan_dup_golden_finger`(131-144) 对每个 power/金手指 行生成计划，当同 novel 不存在 item/金手指 时 keep_id 为 null，apply 直接 DELETE 该行及 history。docstring 与注释声称「removal of the duplicated golden-finger under power (item wins)」，语义是只删重复项，但代码对「无 item 版本、power 是唯一金手指记录」的情况也删，金手指设定（核心设定）永久丢失。已复现：仅插入 power/金手指 一行后 --apply，行与 history 全部消失。现有测试 test_plan_drops_duplicate_golden_finger 只覆盖「存在 item 对应」的场景。建议 keep_id 为 null 时把 power 行改写到 item 分类或跳过删除。

- [P3] distill_lessons 对 report/transcript 的非预期 JSON 类型无防御，直接崩溃 — E:\code\novel-editorial\tools\distill_lessons.py:86-104
  tools/distill_lessons.py:86-104：`_meeting_material` 对 `transcript` 和 `report` 只做 json.loads，未校验结果类型。若库中 transcript 是 JSON 对象（而非数组），`(mat["transcript"] or [])[-6:]` 对 dict 切片抛 TypeError；若 report 是 JSON 数组（而非对象），distill() 里 `mat["report"].get(...)` 抛 AttributeError。已复现：meeting_sessions.report 存 `[1,2,3]` 时 distill 直接 AttributeError 崩溃（exp6 输出）。正常写入方都写 list/dict，但库数据可被旧版本或外部修改，且同一文件里 attendees 用了 `_safe_load_json` 做 isinstance 校验而这两处没有。建议复用类型校验。

- [P3] upsert_ex 合并判定基于截断 120 字符的 content，长内容相似实体永不合并 — E:\code\novel-editorial\tools\novel_knowledge.py:195-195
  tools/novel_knowledge.py:195 用 `_similarity(content, best["content"])` 决定是否合并，而 find_similar 返回的 content 是 `(r["content"] or "")[:120]`（tools/novel_knowledge.py:96）截断值。当新内容超过约 120 字符时，SequenceMatcher 的 ratio 上限为 2*120/(len(content)+120)，500 字符内容即使与旧内容完全相同也只有 0.39 < 0.6，导致本应合并的相似实体被判定为冲突——插入重复行并产生 auto_conflict 草稿噪音，知识库重复累积。web_api 手动 upsert（check_similar=True）和未来任何长内容 upsert 都会踩中。建议用完整 content 比较或对两边一致截断。

- [P3] knowledge_keeper 对非 market 文件的 auto_updates 静默跳过，无日志无审计 — E:\code\novel-editorial\tools\knowledge_keeper.py:242-243
  tools/knowledge_keeper.py:242-243：`if file not in market_files or not body: continue`——LLM 提议更新非 market 知识包（或 body 为空）时直接静默忽略，既不进 invalid 列表，也不写 audit 日志。用户无法感知模型输出被部分丢弃（例如模型违反规则提议改 craft 包时，操作被拦下却没有任何痕迹）。建议至少记录到 invalid 或 audit，与 draft_suggestions 分支的显式处理保持一致。

- [P3] export_agent_prompts 在 proxy 模式下以退出码 1 结束，脚本化调用会误判失败 — E:\code\novel-editorial\tools\export_agent_prompts.py:63-68
  tools/export_agent_prompts.py:63-68 在检测到 proxy 模式（当前 n8n/novel_workflow.json 的 jsonBody 均为 `{agent:'...'}` 形式，已确认命中）时打印提示并 `return False`，而 120-121 行 `raise SystemExit(0 if main() else 1)` 把 False 映射为退出码 1。proxy 是正常且唯一的运行状态（非导出场景），但任何按退出码判断的脚本/CI 调用（docs/evolution.md:130 有文档化用法）都会误报失败。建议 proxy 分支返回 True 或单独定义退出码语义。
