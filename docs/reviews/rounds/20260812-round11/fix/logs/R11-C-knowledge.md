弄好了mashitawa。六项全部先复现、再修补、后验证，compileall 通过，相关 pytest 66 项全绿，一个都没落下desuwa。

R11-C-01（P2） [tools/export_agent_prompts.py](/E:/code/novel-editorial/tools/export_agent_prompts.py:65) — proxy 分支不再静默成功：明确打印「本工具不导出任何文件」，main() 返回 False，`__main__` 用 `SystemExit(0 if main() else 1)` 把退出码置为 1；非 proxy 正常导出后返回 True、退出码 0。验证：CLI 实跑退出码 1；现有 `test_review_v3.py::ExportPromptProxyTests` 直接调 main() 只查打印，仍通过。

R11-C-02（P3） [tools/ai_taste_check.py](/E:/code/novel-editorial/tools/ai_taste_check.py:95) — 排比启发式重写为两种结构：恰好 8 字的连续汉字段（两个紧贴的四字短语，每段计 1 处），以及标点分隔的独立四字短语链（k 个短语计 k-1 对）。不再对任意长度的叙述从句做 4 字滑窗。验证：审查原文「她站在窗前看了很久，心里想着明天该如何开口解释这件事。」从误报 2 处降到 0 分 0 note；「天崩地裂，日月无光，山河变色。」从漏报变为命中 2 处；现有堆砌测试「璀璨耀眼磅礴深邃，璀璨耀眼磅礴深邃」仍报 2 处。

R11-C-03（P3） [tools/ai_taste_check.py](/E:/code/novel-editorial/tools/ai_taste_check.py:32) — FILLER 词表补上「不是……而是」（双省略号）。验证：`detect("他不是……而是直接走开了。")` 的 filler 命中从 0 变 1。

R11-C-04（P3） [tools/distill_lessons.py](/E:/code/novel-editorial/tools/distill_lessons.py:228) — `{"lessons": []}` 不再假成功，返回 `ok=False`、error 说明空列表并带 meeting 来源。验证：mock 复现从 ok=True 变 ok=False。

R11-C-05（L-062） [tools/novel_knowledge.py](/E:/code/novel-editorial/tools/novel_knowledge.py:251) — `get()` 的 entity LIKE 参数复用 `_like_escape` 并加 `ESCAPE '\'`，与 `resolve()` 行为一致。验证：`get(..., entity="%")` 不再返回全表；`entity="_"` 只命中含字面下划线的行，不误匹配普通实体。

R11-C-06（P3） [tools/knowledge_keeper.py](/E:/code/novel-editorial/tools/knowledge_keeper.py:203) — LLM 输出在应用前校验 auto_updates / draft_suggestions / deprecations 三个键必须存在且为 list；缺失或类型错误时写 `keeper_output_schema_invalid` audit 记录（含 invalid_keys 与 raw 前 300 字）并返回 ok=False，不执行任何更新。验证：`{"foo": 1}` 从 ok=True 假成功变为 ok=False 且 audit 落库；合法输出（含合法空三键）仍 ok=True。

验证总况：`python -m compileall` 五文件通过；pytest 覆盖 test_ai_taste_check / test_distill_lessons / test_knowledge_keeper / test_novel_knowledge / test_review_v3 / test_clean_knowledge / test_knowledge_bible / test_knowledge / test_novel_flow / test_review_v4，共 66 项全绿。

测试建议（测试文件不在指派范围，未改动）：给 test_ai_taste_check 补「普通叙述 0 note + 真实三连排比命中」和双省略号命中用例；给 test_distill_lessons 补空 lessons 返回 ok=False；给 test_novel_knowledge 补 entity 含 %/_ 的字面量用例；给 test_knowledge_keeper 补缺键/错类型输出失败且 audit 留痕；给 test_review_v3 补 CLI 退出码断言。

额外发现（只报告不改）：一是 export_agent_prompts 非 proxy 路径若工作流里 15 个 agent 节点全部缺失，仍会打印 `exported: []` 以退出码 0 结束，是同类假绿灯；二是 distill_lessons 里 lessons 非空但元素全部缺 title/content 时，循环静默 continue，仍返回 ok=True、drafted=0，建议后续也显式失败或留痕desuwa。

本轮记忆已按 angel-memory 规则写入（ID m143）desuno。就这些，我先停在这里teyo。
