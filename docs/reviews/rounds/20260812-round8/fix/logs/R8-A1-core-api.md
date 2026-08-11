修复都弄好了mashitawa。三个文件只动了我分到的那三个，每一条都单独验过desuwa。

先讲 web_api 的两处。do_POST 在 JSON 解析之后加了顶层类型检查，数组、字符串、数字一律回 400，见 [web_api.py](E:/code/novel-editorial/novel_editorial/web_api.py:673)；`/api/agent_states/update` 的 novel_id 先做整数清洗，`abc` 这种直接 400，数字字符串正常转整数落库，见 [web_api.py](E:/code/novel-editorial/novel_editorial/web_api.py:738)。

meeting_session 这边四件事。planning 会议创建时不再绑最新书，novel_id 保持 0，[meeting_session.py](E:/code/novel-editorial/novel_editorial/services/meeting_session.py:37)；`_run_locked` 末尾对 planning 绝不调 apply_report，统一走 create_planning_from_next_book，[meeting_session.py](E:/code/novel-editorial/novel_editorial/services/meeting_session.py:721)；materials 为 None 的分支补了 audit 留痕和 updated_at，[meeting_session.py](E:/code/novel-editorial/novel_editorial/services/meeting_session.py:407)；再有 run_session 加了异常兜底，后台线程失败时标记 failed、写 audit、写 alerts.log，然后照常抛出，[meeting_session.py](E:/code/novel-editorial/novel_editorial/services/meeting_session.py:348)。

嗯，这里有个要说明的desuwa——报告里说 `_run_locked` 的 RuntimeError 不落盘，但我实测它已经被函数底部的大 except 接住并写了 audit；真正完全不落盘的是 run_session 查不到会话行的那条路径，所以我把修复落在那里，这类错误现在都有迹可循了。agency 那边，apply 遇到非 dict 的 action 项，除了计 rejected 也写 audit 带原因，[agency.py](E:/code/novel-editorial/novel_editorial/services/agency.py:97)。

验证结果：compileall 三个文件通过；用 rg 圈出相关 10 个测试文件，pytest 143 项全绿；另外写了一套 17 点行为脚本，每条修复的失败路径和成功路径都过了一遍。中途批量测试一度 139 项失败，查下来是 C 盘临时目录 0 字节可用，pytest 建不了临时库，不是代码问题——我把 TMP/TEMP 指到 E 盘后重跑就全绿了desuwa。

额外发现、只报不改：C 盘满到连 angel-memory 的 SQLite 都打不开，本轮记忆没写成；工作区里 tools、webapp 那批改动是并行任务组写的，我确认过没碰；E:\codex_tmp 是我验证时留下的临时目录，删除被沙箱策略拦了，不在仓库里，不影响交付。MEMORY.md 没动，任务包也不允许改其他文件——就这么定了teyo。
