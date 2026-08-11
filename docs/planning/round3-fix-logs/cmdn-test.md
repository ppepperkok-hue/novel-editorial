弄好了mashitawa。六项修复在我接手时已经落在工作区里（未提交），我逐项核过源码、引用和调用链，又补跑了代表性输入验证，没有发现缺口，所以没有重写、只做核验desuwa。

| 修复项 | 文件+行号 | 改动摘要 | 验证结果 |
|---|---|---|---|
| R3-A1-01 | [agency.py](E:/code/novel-editorial/novel_editorial/services/agency.py:60) | `claim_task` 对 `action_id` 做类型/数字/正数校验；`apply` 对单个动作 `try/except`，失败经 `audit.log` 留痕后跳过，整批不中断 | compileall 通过；实测含 `abc`、`999999`、全角数字的批次 `applied=1 rejected=3`，无异常 |
| R3-A1-02 | [agents.py](E:/code/novel-editorial/novel_editorial/services/agents.py:82) | `agent_save` 全部失败路径返回 `ok=False` 并带 error；render/validate 非 0 时回滚原文件；仅成功返回 `ok=True` | `test_review_v3` 通过，路径/温度/提示词校验均走失败分支 |
| R3-A1-03 | [agents.py](E:/code/novel-editorial/novel_editorial/services/agents.py:39) | 删除 `_extract_node_system` | 全仓 `rg` 无引用（仅规划文档提到该函数名） |
| R3-A1-04 | [control.py](E:/code/novel-editorial/novel_editorial/services/control.py:289) | `apply_schedule` 的 `-DbPath` 改用 `_db_path()`，不再走 `config.DB_PATH` 默认值 | 调用链确认 [web_api.py](E:/code/novel-editorial/novel_editorial/web_api.py:1150) 启动时 `set_db_path(active_db)` 注入 `--db` |
| R3-A1-05 | [knowledge.py](E:/code/novel-editorial/novel_editorial/services/knowledge.py:222) | `accepted_at` 改为 `CASE WHEN ?='accepted'`，其余状态置 NULL | 实测 reject 后 `accepted_at=None` |
| R3-A1-06 | [misc.py](E:/code/novel-editorial/novel_editorial/services/misc.py:36) | `load_hot_topics` 捕获 `OSError/ValueError`、拒绝非 dict，写 ALERTS_LOG 后返回默认结构 | 实测损坏 JSON 返回 fallback 且告警落盘 |

验证汇总：五个文件的 `compileall` 通过；`pytest` 跑了 test_agency、test_knowledge、test_knowledge_keeper、test_distill_lessons、test_review_v3、test_services_regression、test_agent_actions、test_web_api，77 个测试通过。全量跑时 `test_cross_origin_post_rejected` 出现过一次 `ConnectionAbortedError`，单独重跑通过，是 Windows 下 socket 抖动，跟本轮改动无关desuwa。

额外问题，只报告不改：第一，agent_save 里 `path.read_text/write_text` 的 I/O 异常没捕获，而 `subprocess.run` 直接抛 OSError（比如 node 不在 PATH）时文件已写入却没回滚——回滚只覆盖了 returncode 非 0 的分支。第二，claim_task 被拒的具体原因（比如 action not found、已认领）没进 audit detail，只记了 `ok=False`，畸形 id 也缺专门 error 字段，追踪性可以更细。第三，misc.py:137 的 `start_topic_meeting` 默认参数还是 `"demo.db"`，和 R3-A1-04 同主题，但不在指派范围，而且目前没有调用方。

测试建议写在结果里：给 test_agency 补畸形/不存在 action_id 的批次用例，给 test_knowledge 补 rejected 后 accepted_at 为 NULL 的断言，给 misc 补损坏 hot_topics.json 的用例，给 agent_save 补 mock 非 0 返回码的失败用例。测试文件不在指派范围，我一律没动。就这么定了teyo。
