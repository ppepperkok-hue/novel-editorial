审查范围：prompts/、tools/{novel_knowledge,knowledge_keeper,distill_lessons,clean_novel_knowledge,ai_taste_check,export_agent_prompts}.py，依赖接口仅读 db.py/config.py/llm_client.py/services/{knowledge,audit,activity}.py 验证契约。基线：slice 文件 compileall 全部通过；slice 相关 24 个测试（test_novel_knowledge/test_ai_taste_check/test_clean_knowledge/test_knowledge_keeper/test_distill_lessons）全部通过，但现有测试未覆盖 outline 非法 JSON、LLM 数组元素非 dict、缺 lessons 键、WAL 备份完整性四类场景，均为本次实测复现的缺陷。P1 1 项（sync_latest 崩溃且每日 wrapup 中静默失败），P2 3 项（LLM 输出崩溃、蒸馏假绿灯、WAL 备份残缺），P3 1 项（detect 空文本 schema 不一致）。建议修复 P1/P2 后再合并。

Full review comments:

- [P1] sync_latest 对非法 JSON outline 无防御，知识库同步整体中断 — E:\code\novel-editorial\tools\novel_knowledge.py:615-615
  tools/novel_knowledge.py 的 sync_latest() 在 615 与 628 行直接执行 `json.loads(novel["outline"] or "{}")`，未捕获 ValueError。已复现：当 novels.outline 为 'NOT-JSON' 时调用 sync_latest 抛出 `JSONDecodeError: Expecting value: line 1 column 1`，bible 初始化与章节同步全部不执行。这不是理论场景：同仓库 tools/architect_weekly.py:207-211 对同一字段做了显式防御并注释 "outline is not valid JSON for novel"，而 graph()（331 行）也包了 try/except，唯独 sync_latest 漏掉。调用方 tools/editorial_daily.py:1435 的 _run_tool 会把异常吞成 warning，导致每日 wrapup 里知识库同步静默失败；CLI `python tools/novel_knowledge.py --sync-latest` 则直接 traceback。建议与 graph()/architect_weekly.py 保持一致，对两处 json.loads 加 try/except 并降级为空 bible。

- [P2] 知识管家/蒸馏对 LLM 输出数组元素类型零校验，字符串元素直接 AttributeError 崩溃 — E:\code\novel-editorial\tools\knowledge_keeper.py:160-161
  knowledge_keeper.run() 对模型输出的 auto_updates/draft_suggestions/deprecations 直接 `item.get("file")`（160、197、213 行），distill_lessons.distill() 对 lessons 直接 `item.get("title")`（184-196 行）。response_format=json_object 只保证顶层是 object，不保证数组元素是 dict；模型输出字符串数组（截断或幻觉）时整个流程崩溃。已复现：mock chat_deepseek 返回 `{"auto_updates": ["market.md"], ...}` 时 `AttributeError: 'str' object has no attribute 'get'`；distill 返回 `{"lessons": ["..."]}` 同样崩溃。web 端表现为 500 internal error，CLI 端为 traceback，无降级路径。建议对元素先做 isinstance 校验后跳过或转人工。

- [P2] distill_lessons 对无 lessons 键的合法 JSON 返回 ok:True，假绿灯 — E:\code\novel-editorial\tools\distill_lessons.py:178-182
  tools/distill_lessons.py:180 的判定 `if not lessons and parsed is None` 只在解析失败时返回错误；若模型返回合法 JSON 但缺少 lessons 键（如 `{"unexpected": 1}`，已复现），函数返回 `{'ok': True, 'drafted': 0, 'total_lessons': 0}`，web_api:963 的调用方与 UI 均显示成功，实际零产出。空 lessons 与模型输出异常无法区分，属于静默失败。建议在 parsed 非 None 但 lessons 缺失/为空时显式返回 ok:False 或增加 "empty" 状态。

- [P2] clean_novel_knowledge 在 WAL 模式下用 shutil.copy2 备份，备份文件缺失已提交数据 — E:\code\novel-editorial\tools\clean_novel_knowledge.py:309-312
  db.connect()（novel_editorial/db.py:95）启用 `PRAGMA journal_mode=WAL`，而 tools/clean_novel_knowledge.py:311 用 `shutil.copy2(path, backup)` 只复制主 .db 文件，不含 -wal/-shm。已复现：连接写入两行并 commit 后（wal 文件存在），复制主文件并单独打开副本，行数为 0——WAL 中未 checkpoint 的已提交事务全部丢失。单机多进程（web_api 常驻 + scheduler + CLI）场景下备份时 WAL 大概率残留数据，一旦用户用该备份恢复会丢数据，造成虚假安全感。建议改用 sqlite3 backup API（conn.backup()）或先执行 `PRAGMA wal_checkpoint(TRUNCATE)` 再复制。

- [P3] ai_taste_check.detect 空文本返回值缺少 chars 键，输出 schema 不一致 — E:\code\novel-editorial\tools\ai_taste_check.py:70-72
  tools/ai_taste_check.py:70 空文本分支返回 `{"score": 0, "flowery": {}, "filler": {}, "density": 0, "notes": []}`，缺少非空分支含有的 `chars` 键（已复现：空文本 keys 为 density/filler/flowery/notes/score，非空文本多 chars）。CLI/JSON 消费方按固定 schema 解析时会得到不一致结果。建议空文本分支补 `"chars": 0`。
