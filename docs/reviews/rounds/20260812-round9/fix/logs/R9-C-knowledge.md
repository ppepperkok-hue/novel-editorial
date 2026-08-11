我查完了，三处都修好了mashitawa，编译和测试也都跑通了desuwa。

R9-C-01：`_parse_json` 在 [knowledge_keeper.py](/E:/code/novel-editorial/tools/knowledge_keeper.py:26) 第26行重写成「先整体 json.loads，只收 dict；失败再从头一个 `{` 做平衡花括号扫描」，扫描时跟踪字符串与转义，值内的 `{`、`}` 不再影响层数desuwa。实测「值里带花括号 + 结尾还拖着带花括号的散文」和「```json 围栏内嵌 `"}"`」都能正确解出，纯文本照旧回 None。novel_knowledge.py 我整份确认过，并没有 `_parse_json`，那半边不需要动desuno。

R9-C-02：[knowledge_keeper.py](/E:/code/novel-editorial/tools/knowledge_keeper.py:85) 第85行起的热点读取加了 `isinstance(hot, dict)` 校验，解析出 list 就回退空结构，警告写进 payload（第126行），真实执行时再落一条 `keeper_hot_topics_invalid` audit（第148行），dry-run 不落库desuwa。实测热点文件是 `[1,2,3]` 时不再崩，返回空热点加警告，audit 恰好一条，dry-run 不会重复写teyo。

R9-C-03：[clean_novel_knowledge.py](/E:/code/novel-editorial/tools/clean_novel_knowledge.py:309) 第309行备份时间戳补了 `%f` 微秒，同一秒连跑两次 `--apply` 得到两个不同文件，实测 062211-490169 和 062211-498175 并存，互不覆盖mashitawa。

验证方面，三个文件强制重编译全过，pytest 跑了 test_knowledge_keeper、test_clean_knowledge、test_novel_knowledge、test_knowledge_bible，25 个全绿desuwa。

顺手看到的额外问题，只报告不改desuwa：distill_lessons.py 第26-30行有完全一样的首尾花括号截取函数，同病，不在指派范围；knowledge_keeper 热点即使校验成 dict，sources 若是字符串而非 list，列表推导里 `s.get` 还是会崩，建议以后补类型校验；round9 切片还指出 novel_knowledge.py 的 resolve 对 LIKE 通配符 `%`/`_` 未转义、docstring 的 `--snapshot --novel-id` 示例与 CLI 不符，都留给下一轮teyo。

测试建议，现在三个修复点都没有回归用例罩着：给 `_parse_json` 补值内花括号加尾随散文、围栏 JSON 两种用例；给热点补 list 回退加 audit 用例；给备份补同秒双跑不覆盖用例。MEMORY.md 不在指派范围，我没动desuwa。
