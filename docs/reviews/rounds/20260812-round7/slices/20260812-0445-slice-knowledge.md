审查范围：prompts/（agents+knowledge 全部提示词）与 tools 下 6 个文件；基线：6 个目标文件 compileall 通过，36 个切片相关单测（test_ai_taste_check/test_clean_knowledge/test_distill_lessons/test_knowledge_keeper/test_novel_knowledge/test_knowledge_bible/test_knowledge）全部通过，sync_latest 幂等、knowledge_keeper --dry-run、clean --dry-run、export（代理短路）在 demo.db 副本上均正常；依赖契约（db.py/config.py/services/knowledge|audit|activity/llm_client）逐一核对无错位。但 clean_novel_knowledge 的合并逻辑存在可复现的静默数据丢失（P1），ai_taste_check 核心指标对普通文本系统性误报（P2），export_agent_prompts 存在永不执行的陈旧导出分支（P3），故判定整体不正确。

Full review comments:

- clean_novel_knowledge 链式合并时 keep 行缺失会静默删除 drop 行内容 — E:/code/novel-editorial/tools/clean_novel_knowledge.py:194-201
  `_merge_history` 的 keep-is-None 分支（tools/clean_novel_knowledge.py:194-201）直接 `DELETE` drop 行及其 history。`plan_clean` 生成的是两两重叠的计划：3 条互相相似的 world_rule（甲 v1 / 乙 v2 / 丙 v1）会产出 (keep乙,drop丙)、(keep丙,drop甲)、(keep乙,drop甲) 三条条目，apply 时先合并丙进乙，随后条目 (keep丙,drop甲) 因 keep 已被消费而把甲整行删掉——实测最终只剩乙，`内容甲` 与 history 全部丢失，返回的 counts 完全看不出损失。若 rename/state_rows 的合并先消费了 keep 行（如“阴阳两界规则：细节A”v2 被改名合并进“阴阳两界规则”），更会连锁把整个规则集连 history 一起清空（已在临时库复现：after 0 行）。修复方向：keep 缺失时不删除 drop 行（保留或并入吸收 keep 的行），并让 plan 条目去重/按拓扑顺序执行。

- ai_taste_check 四字连排启发式对普通中文文本大量误报并抬高分数 — E:/code/novel-editorial/tools/ai_taste_check.py:87-102
  tools/ai_taste_check.py:87-102 把任意 8 个及以上连续汉字（无标点）都计为一处“四字排比”，两处即触发 `疑似四字排比堆砌` 并给 score 加 runs*6。实测一段无任何华丽词/填充词/感叹号的普通叙述（104 字）得 score 42、notes 含“疑似四字排比堆砌 7 处”；2200+ 字的普通章节几乎必然触发，导致该检测器核心指标对正常文本系统性失真（该结果经 novel_editorial/services/misc.py:177 `ai_taste` 直接暴露给 web_api）。建议改为识别真正平行的四字词组（如按词表/停顿切分）或提高连续块数阈值。

- export_agent_prompts 非代理导出分支是永远不执行的陈旧死代码 — E:/code/novel-editorial/tools/export_agent_prompts.py:36-37
  当前 n8n/novel_workflow.json 已处于代理模式（隔离运行实测输出 PROXY_MODE=True，tools/export_agent_prompts.py:43-52 直接 return），导出分支永远不会执行；即使移除代理短路，START_MARK/END_MARK（第 36-37 行）用单引号匹配 `{role:'system',content:'`，而 jsonBody 是 JSON 字符串，引号必然被转义为 `\"`，`find` 恒为 -1，所有节点都会以 “no system match” 跳过、静默产出空结果。建议删除该分支或改为解析 JSON 转义后的文本。
