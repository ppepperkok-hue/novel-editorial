slice 内全部 6 个文件编译通过、46 个针对性测试全绿、CLI 冒烟（snapshot/dry-run/apply/keeper dry-run/distill/ai_taste_check/export）均正常，但 novel_knowledge.upsert_ex 的插入分支在并发首次写入时确定性抛未捕获 IntegrityError（已用双线程 barrier 复现），且 web_api 为 ThreadingHTTPServer 并发场景真实存在，属于会打断线上写入的 P1 缺陷，需要修复后合入。

Full review comments:

- upsert_ex 并发首次插入会抛未捕获 IntegrityError，插入路径无重试 — E:/code/novel-editorial/tools/novel_knowledge.py:238-243
  `upsert_ex` 只在「行已存在」的更新分支里有 5 次重试（tools/novel_knowledge.py:247-248），而新实体的 INSERT（tools/novel_knowledge.py:238-243）和 `_ensure_history_version_unique` 的 CREATE UNIQUE INDEX 都在 try/except 之外。复现：两个线程用 barrier 同步后对同一新实体并发 upsert，其中一个线程在 line 238 抛 `sqlite3.IntegrityError: UNIQUE constraint failed: novel_knowledge.novel_id, novel_knowledge.category, novel_knowledge.entity`（另一个成功）；6 线程压测结果 3×`OperationalError: database is locked`、1×`RuntimeError 重试耗尽`、1×IntegrityError，仅 1 个成功。生产环境 web_api 用 ThreadingHTTPServer 且 `/api/novel_knowledge` upsert 只捕获 ValueError（novel_editorial/web_api.py:1077-1091），并发编辑/与每日管线 sync 撞车会直接 500 或使管线节点崩溃。建议把 INSERT 分支也纳入与更新分支相同的「捕获 IntegrityError/锁冲突后重读重试」逻辑。

- knowledge_keeper 对无法读取的知识包静默跳过且无审计记录 — E:/code/novel-editorial/tools/knowledge_keeper.py:255-257
  tools/knowledge_keeper.py:255-257 中 `full = knowledge.read_knowledge(file)` 返回 None（模型幻觉出的文件名、已删除文件或路径穿越尝试）时直接 `continue`，既不计数也不写 audit；而同函数对非 market 包跳过时明确「Leave a trace instead of silently skipping」（line 245-254）。LLM 输出里出现不存在文件名是常态，静默丢弃会让 keeper 的产出与审计不一致，建议补一条 `keeper_auto_update_skipped_missing` 审计。

- distill_lessons 空 content 的经验被静默丢弃不计入 skipped — E:/code/novel-editorial/tools/distill_lessons.py:272-275
  tools/distill_lessons.py:272-275 中 title 有默认值「未命名经验」不会为空，但 content 为空时直接 `continue`，既不入库也不追加到 `skipped_lessons`；而 line 269-270 对非 dict 项是计数的。结果 `skipped` 计数和 activity 日志（line 287-297 的 `"skipped": len(skipped_lessons)`）会系统性低估被丢弃的经验条数，无法在面板上看出模型输出被过滤了多少，属于静默失败。

- clean_novel_knowledge 合并历史时版本冲突产生重复行或静默丢历史 — E:/code/novel-editorial/tools/clean_novel_knowledge.py:262-270
  `_merge_history`（tools/clean_novel_knowledge.py:262-270）用 `INSERT OR IGNORE` 把被删行的历史搬到 keep 行，但 keep 与 drop 几乎总是都从 version 1 开始，版本必然冲突：数据库没有 `ux_novel_knowledge_history_kid_version` 唯一索引时 OR IGNORE 不生效，会写入重复的 `(knowledge_id, version)` 行（已复现：合并两个各带 version-1 历史的行后 history 出现两条 version=1 的记录）；有索引时则 drop 侧历史被静默丢弃。且 `_ensure_history_version_unique` 发现重复后永久放弃建索引，问题会一直残留。建议迁移历史时对冲突版本改写版本号或显式合并内容。

- export_agent_prompts 缺少单元测试 — E:/code/novel-editorial/tools/export_agent_prompts.py:88-119
  本 slice 其余工具（novel_knowledge / knowledge_keeper / distill_lessons / clean_novel_knowledge / ai_taste_check）都有对应测试文件，唯独 tools/export_agent_prompts.py 没有任何测试；其核心解析逻辑（`_find_system_end` 边界判定、line 112 的 `\'`/`\"`/`\\` 三级反转义、model/temperature/max_tokens 字段截取，line 88-119）完全靠手工验证，且当前工作流处于 PROXY_MODE 分支导致导出路径实际不可达，回归风险高。建议至少补一个最小 jsonBody 样本的解析与 frontmatter 输出测试。
