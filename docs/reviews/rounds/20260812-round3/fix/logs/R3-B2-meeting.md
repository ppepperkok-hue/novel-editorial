弄好了mashitawa。四个 P3 都修完、验证过才交的，工作区只动了指派的那四个文件，没碰 git，也没清理别的东西。

| 修复项 | 文件:行 | 改动摘要 | 验证 |
|---|---|---|---|
| R3-B2-01 | tools/agent_meeting.py:30, 188-206, 218, 260 | 抽出 `_chat_with_retry`，首轮和 final round 共用 `LLM_RETRY_ATTEMPTS=3` 重试（1s/2s 退避），耗尽才抛 RuntimeError 留痕 | mock `chat_deepseek`：final round 首次失败第二次成功 → 3 次调用后正常返回；全失败 → 3 次后抛错 |
| R3-B2-02 | tools/architect_weekly.py:181-189 | `novels.outline` 解析包 `(TypeError, ValueError)`，失败打 stderr note 并用 `{}` 兜底，bible/blueprints 走空默认 | 脏 outline 下 `build_materials` 正常返回，空蓝图空大纲，stderr 有留痕 |
| R3-B2-03 | tools/meeting_actions.py:12, 34-54, 104-110 | SELECT 检查改成原子 `INSERT ... SELECT ... WHERE NOT EXISTS` 占位 marker，`rowcount==0` 即 skip；结束时 UPDATE detail 保留原审计信息 | 双线程同 session 并发跑了 5 轮：每轮恰好一个 applied、一个 skipped，drafts 和 marker 各 1 |
| R3-B2-04 | tools/export_flow_html.py:74-83, 131 | 删掉死代码 `groups`；status 白名单映射 ok/warn/bad/run/idle，未知一律 idle | 未知状态含引号渲染为 `class="status idle"`，raw 状态不再进 class；`running → run` 正常 |

验证总览：`compileall` 四个文件全过；引用这四个模块及相关会议链路的 7 个测试文件（test_agent_meeting、test_meeting_actions、test_export_flow_html、test_open_meeting、test_meeting_session、test_activity、test_agent_actions）共 78 项全绿，11 秒跑完。

额外问题，只报不改：architect_weekly.py:373 的 `tags` 还是裸 `json.loads`，:304-305、:385 的 `int(settings.get(...))` 也没兜底，脏数据照样能炸周会；meeting_actions.py:12 的 `config` 是死导入；agent_meeting.py:232 在 ask 里重复 import 了顶层已有的 knowledge；export_flow_html.py:143、182 的 JS 端 STATUS 没白名单（DOM 赋值不会破坏 HTML，但奇怪状态会污染 class 和颜色）。另外 R3-B2-03 这个修法有个取舍得说清楚：marker 先提交，进程中途崩溃会留下 pending 标记导致后续跳过——保证不重复，但理论上可能不完整；旧逻辑相反，是有重复风险。就这个取舍，我选前者，毕竟并发重复是实打实的 bug。

MEMORY.md 没更新——仓库根没有这个文件，任务也只允许动四个指派文件，所以没碰任何记忆文档。测试建议就不改测试文件了：后续可补 final round 重试的失败注入、脏 outline 兜底、双连接并发幂等、未知状态 class 渲染这四类用例，覆盖点我都写在验证里了desuwa。
