修完了，五处全在指定文件里，没碰别的mashitawa。逐个交代desuwa。

R8-E-01，README.md 19 行测试基线从 448 改成 487，并注明数量以 run_tests.py 输出为准；158 行配置表、191 行测试命令、222 行目录树里的 448 也一并改齐了，仓库里不再有 448 这个数desuwa。验证是实跑出来的：487 tests，OK，退出码 0mashitawa。

R8-E-02，run_tests.py 18 行给 TextTestRunner 加了 buffer=True。修前日志里有两条 `{"ok": true, ...}` 这类被测代码的 print 混在结果里，修后同类污染是 0 条，全量 487 依然全绿desuwa。

R8-E-03，ai_words.json 第 2 行加了 `_note`，声明本文件是 AI 味词表的唯一权威来源，n8n 里的硬编码只是无 PIPELINE_ROOT 时的回退副本。工作流文件不在本组授权里，所以只说明位置：n8n/novel_workflow.json 239 行（质量门A）和 371 行（质量门B）。我逐条比对过，两处硬编码词表和 ai_words.json 目前完全一致，零差异desuno。

R8-E-04，desktop/package.json 37 到 40 行，`tools/**` 换成 `tools/*.py`、`tools/*.ps1`、`tools/*.mjs`、`tools/*.json` 四条白名单，原来的 chrome-profile 排除也自然不需要了。用 electron-builder 真实的 FileMatcher 模拟：44 个顶层工具文件全命中，archive、__pycache__、chrome-profile 以及任何子目录文件零命中，JSON 校验通过mashitawa。

R8-E-05，.env.example 18 到 20 行：FANQIE_VOLUME_ID 从模板移除，换成弃用注释，说明全仓库无读取方、只有 ending.py 会写；README 158 行配置表同步改成只留 FANQIE_BOOK_ID。检索确认 n8n 工作流也不引用它，和代码实际消费一致desuwa。

额外发现只报不改：desktop 的白名单只救了 tools，`novel_editorial/**` 和 `scripts/**` 还是会递归带进各自的 __pycache__（本机这三个目录都存在）；ending.py 47 到 62 行仍在写 FANQIE_VOLUME_ID，模板弃用后成了死写；editorial_steps.py 的 DEFAULT_FLAVOR_WORDS 和 quality_gate.py 的内置回退词表是同族漂移风险，其中 editorial_steps 还没有权威来源标注。另外环境上 C 盘现在 0 字节剩余，测试默认临时目录落在 C: 直接跑会磁盘满，我把 TMP/TEMP 指到 D: 才跑完；并行跑测试时 test_resume_blocked_by_existing_lock 会被 n8n_tmp/t.lock 干扰偶发失败，这次已确认是并发 pytest 在抢锁，单跑没问题desuno。

我这边只改了授权五个文件，没有 git add/commit，MEMORY.md 也没动（不在授权清单）mashitawa。
