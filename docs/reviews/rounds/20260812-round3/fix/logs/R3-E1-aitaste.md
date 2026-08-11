两个文件都改好了mashitawa，F1 和 F2 一起收掉desuwa。

R3-E1-01 落在 novel_editorial/quality_gate.py：15-19 行的兜底词表从 15 词扩成 21 词，与 ai_words.json、tools/editorial_steps.py、n8n 质量门完全同源；45-54 行的 ai_flavor_density 从逐词 findall 求和改成合并交替正则的非重叠计数，重叠词按位置只算一次，空词表也有防护mashitawa。复现数字给你看：「他缓缓说道。」旧口径 2 次命中、密度 400.0，现在 1 次、200.0；「她微微一愣，缓缓说道。」旧 4 次命中、444.44，现在 2 次、222.22。2000 字样例里放 3 处「微微一愣」，新口径密度 1.65、style 10.0，旧口径会算成 3.3、style 只有 8.0——style 不再被系统性压低了desuwa。

R3-E1-02 落在 tools/ai_taste_check.py：48-56 行把原来的 _non_overlap_count 提升成公开纯函数 count_non_overlap，59-62 行新增 density_per_window 纯函数，71-73 行的 detect 改调这两个函数，原 per500 内联公式原样搬进去，现有行为对合法词表逐字节稳定teyo。

验证我跑过了：compileall 两个文件通过；pytest 跑了 tests/test_quality_gate.py、test_ai_taste_check.py、test_hardening.py、test_editorial_steps.py，48 passed；手工样例里三个消费方命中数完全一致——quality_gate、ai_taste_check 的 FILLER、editorial_steps 加载 ai_words.json 后的合并正则，对五个样例都是 1/1/2/3/3 同步desuwa；CLI 冒烟 python tools/ai_taste_check.py --file 也正常输出 JSON。测试文件我没动，git 也没碰，别的文件一概没改mashitawa。

测试建议给你留着：在 tests/test_ai_taste_check.py 里断言 count_non_overlap("他缓缓说道。", ["缓缓", "缓缓说道"]) == 1、count_non_overlap("她微微一愣。", ["微微一", "微微一愣"]) == 1、density_per_window(2, 500) == 2.0、空词表返回 0，再补一条 detect() 里「微微一愣/缓缓说道」混排时 filler_n 只计 2 次的用例；tests/test_quality_gate.py 里断言 ai_flavor_density("他缓缓说道。") == 200.0、含 3 处复合词的 2000 字样例 style 为 10.0。这些就是回归网，词表以后怎么改都有兜底desuwa。

额外发现我只报不改：quality_gate.py:23 加载 ai_flavor 时没有 isinstance(list) 校验，ai_words.json 若损坏成非 list 值会逐字符迭代或静默出错，损坏文件回退也没有告警，我只补了空表防护；ai_taste_check 的 detect 返回的 filler/flowery 明细 map 仍是逐词重叠计数，和内部非重叠的 filler_n/密度并存，走 /api/ai_taste 的消费方若读明细可能误判；交替正则对词表顺序敏感，极端文本如「缓缓缓缓说道」在词序调换后计数会变，现在三个消费方共享同一顺序所以一致，但将来改词表必须靠测试守住。另外两边的归一化本身不同——quality_gate 按中文字符每千字、ai_taste_check 按总字符每 500 字，数值不能直接划等号，这次统一的是命中计数口径，归一化各自保持desuwa。

仓库里没有 MEMORY.md，所以也没有要更新的地方；长期记忆我已记了一条desuwa。
