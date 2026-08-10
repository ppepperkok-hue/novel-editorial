# 发布路径走查与修复清单（2026-08-10）

走查范围：新书选题会 → next_book 落库 → 番茄建书 → 日更工作流
（Planner/守护/写手 A·B/润色/审稿/质量门/主编/排版/发布/校验）→
提炼剧情 → 记录作品 → 日记 → 设定知识库 → 释放锁。

## 已修复

1. **手动预检留锁**：`tools/preflight.py` 手动运行时也获取日更锁且永不
   释放（锁由工作流"结束"节点释放），导致后续 2 小时日更全被 blocked。
   修复：新增 `--no-lock` 纯检查模式。
2. **新书会结论不落库**：无作品时 `apply_report` 不建书（只在书完结后建
   下一本），新书会白开。修复：`create_planning_from_next_book`，会议
   收尾自动把 `decisions.next_book` 落成 planning 新书（按书名幂等）。
3. **第二个会议被全局锁阻塞**：会议线程持全局锁直到整场结束，等待用户
   输入的会议会永久堵死后续会议（表现为 round 0 卡死）。修复：
   `create_session` 检查已有 active 会议并友好拒绝。
4. **取消会议被覆盖**：线程每轮结束无条件写 `awaiting_input`，发言中
   设置的 cancelled 会被覆盖复活。修复：写入前校验 `status != 'cancelled'`。
5. **僵尸会议不自愈**：web_api 重启后 running 会议永久占位。修复：
   `get_active_session` 对心跳超过 10 分钟的 running 会话自动标 failed。
6. **新会无心跳被误杀**：`create_session` 不写 heartbeat，刚创建就会被
   自愈逻辑误判僵尸。修复：创建时写入初始心跳。
7. **前端"关闭"不停止后台会议**：关闭按钮只清本地状态，后台线程继续
   烧钱跑完全场。修复：新增 `POST /api/meetings/cancel` + 前端"取消会议"
   确认按钮，并提示"直接关闭面板不会停止后台会议"。
8. **无书日更空转**：无 publishing/finishing 作品时 preflight 仍放行，
   整条生成+发布链空转且 record_work 会建垃圾行。修复：preflight 增加
   `check_active_book`，无书直接 blocked 并提示先开新书会并建书。
9. **record_work 空载荷建垃圾书**：空 payload 时 upsert_novel 会创建
   "未命名" publishing 书。修复：空载荷直接跳过，不落任何行。
10. **work_meta 关键词为空**：任务表达式读 `$json.keywords`，但
    `get_meta` 不输出该字段。修复：get_meta 输出 `keywords`（由 tags 派生）。

## 工具侧规避

- PowerShell 5.1 的 `Invoke-RestMethod -Body <string>` 发中文会变成 `?`
  （本次会议标题乱码的根因）。已改用 Python urllib + UTF-8 body 调用
  带中文的 API；面板内（浏览器）调用不受影响。

## 确认无害

- "设定题材"节点的 premise/genre/keywords 表达式读"读当前书"输出，
  但 `current_book.py` 不输出这些字段——该节点的题材字段是死值。
  Planner 与 work_meta 实际从"读本地资料"（get_meta）取数，不受影响。
- 发布失败路径：`失败留痕 → 合并发布结果 → … → 结束`，所有分支最终
  都会走到"结束"节点释放运行锁。

## 待办操作项（非代码）

- n8n 三个工作流仍为 inactive，正式跑日更前需激活（或保持手动触发）。
- 番茄建书每日限 1 本；建书前确认当日额度，失败时次日重试。
- 会议一轮 8 人约 3-4 分钟（LLM 串行），三轮约 12-15 分钟，属预期；
  前端已有"主席正在点将"提示。

