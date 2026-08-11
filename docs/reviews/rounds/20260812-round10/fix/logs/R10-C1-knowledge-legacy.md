修复做完了mashitawa。五处全按指派文件落的最小 patch，编译、定向测试、行为验证都过了，全量测试里唯一挂的那个是仓库既有的历史遗留，跟本轮无关desuwa。

R10-C1-01（L-049）`tools/distill_lessons.py:26` —— `_parse_json` 换成与 knowledge_keeper 同款平衡花括号扫描：先整体 `json.loads`，失败再按字符串感知的深度扫描取首尾花括号，值内的 `{`/`}` 不再截错。保留了原有「顶层非 dict 走专门报错」的分支语义。验证：`{"lessons":[{...内容含 {花括号} 与 }...}]}` 前后带散文文本能完整解析，纯文本和空输入照旧回 None。

R10-C1-02（L-050）`tools/knowledge_keeper.py:97-107` —— 热点 sources 加类型闸：None 视为空，非 list 回退空列表并把警告写进 `hot_topics_warning`（run 里会落 audit），list 内非 dict 元素顺带过滤。两处 `sources` 推导改用同一变量。验证：`sources` 为字符串/字典/数字均不崩且留痕，混合列表只保留 dict 项。

R10-C1-03（L-051）`tools/novel_knowledge.py` —— 新增 `_like_escape`（365-372），`resolve`（375-390）的 LIKE 参数转义 `\` `%` `_` 并加 `ESCAPE '\'`；模块 docstring 第 11 行改为真实的 `--snapshot 1 --db demo.db`，`sync_from_chapters` 的 docstring（414）也改成 `--sync N`。验证：搜 `50%` 只命中 `discount50%` 不命中 `discount50X`，搜 `_` 只命中字面下划线实体。

R10-C1-04（L-056）`tools/ai_taste_check.py:68-71` —— `detect` 入口先查 `isinstance(str)`：真值非字符串抛带类型的 `ValueError`，假值（`""`/`None`/`0`/`[]`/`{}`）维持原空报告。验证：列表/字典/整数/浮点都得到明确报错，原测试的假值契约未破坏。

R10-C1-05（L-052）`tools/record_work.py:339-353` —— `upsert_chapters` 遍历改 `enumerate`，元素非 dict 时写 `alerts.log`（含下标与类型）并跳过。验证：`[None, "bad", 合法章节]` 只落库合法项，alerts 里留下两条留痕，且我把 `ROOT` 重定向到临时目录，没碰仓库的日志文件。

验证汇总：五文件 `compileall` 通过；相关九份测试文件 pytest 57 全绿；全量 497 个测试 496 过、1 挂，挂的是 `test_web_api.py::test_knowledge_save_rejects_path_traversal`——它期待 500，而 `web_api.py:916-918` 现在捕获 ValueError 后回 400，是仓库既有 dirty 改动造成的契约失配，涉及 `web_api.py`/`services/knowledge.py`，均不在本轮指派范围，只报告不改。git diff 确认我只动了这五个文件，工作区里其他修改都是之前轮次留下的，没碰。

额外发现（只报告）：`novel_knowledge.get()` 的 entity LIKE（246-256 附近）同样未转义通配符，与 resolve 同类；`record_work.record_payload` 的活动统计（521-526）仍对 chapters 元素直接 `c.get`，非 dict 会在 upsert_chapters 之后再度崩溃；`upsert_characters` 对 protagonists 元素也没有 dict 防线。这三处建议下一轮收掉desuwa。另外 `knowledge_keeper` 的 `top_keywords` 非 list 无校验（不会崩但会进 prompt），`count_occurrences`/`count_non_overlap` 直调非字符串仍会 TypeError——都是低危，先记着。

没有动遗留跟踪表（不在指派范围），MEMORY.md 这轮也没有更新mashitawa。
