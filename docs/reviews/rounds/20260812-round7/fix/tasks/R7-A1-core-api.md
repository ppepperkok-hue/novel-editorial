# 修复任务包 · R7-A1 核心服务与 API

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（新发现）+ 跨轮次遗留跟进。审查报告：`docs/reviews/rounds/20260812-round7/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `novel_editorial/web_api.py`
- `novel_editorial/services/misc.py`
- `novel_editorial/db.py`
- `novel_editorial/services/control.py`
- `novel_editorial/config.py`

## 修复项

### R7-A1-01（P2，新）web_api.py:149-151
现状：/api/daily_runs 吞掉 sync_from_n8n 返回的 error 标记（静默失败）。
期望：error 标记透出到响应（如 error 字段或非 200），不静默。

### R7-A1-02（P3，新）web_api.py:1167
现状：web_api 默认 --db 是 CWD 相对路径，config.DB_PATH 是 ROOT 根路径，导致静默双库分裂。
期望：默认 --db 与 config.DB_PATH 一致（ROOT 根），或显式解析为绝对路径。

### R7-A1-03（P3，新）services/misc.py:257-265
现状：update_state 对缺失 agent 抛 IntegrityError → HTTP 500 而非 400。
期望：缺失 agent 显式校验返回 400 错误信息。

### R7-A1-04（P3，新）db.py:346-364
现状：db.connect(:memory:) 返回无表的连接。
期望：内存库也执行建表迁移（与文件库一致），或显式说明并返回可用连接。

### R7-A1-05（P3，新）services/control.py:438-456
现状：手动采集热点阻塞 HTTP 线程且总是报 ok。
期望：采集放后台/超时保护；失败时返回真实错误，不假 ok。

### R7-A1-06（L-004）web_api.py
现状：do_POST 对非法 JSON body 仍 500；/api/agent_actions/create 的 novel_id 未整数清洗（session_id/meeting_id 已修）。
期望：非法 JSON body 返回 400；novel_id 做整数清洗，非法输入 400。

### R7-A1-07（L-003）services/misc.py
现状：start_topic_meeting 默认参数 demo.db（无调用方）。
期望：改为与项目一致的默认（config.DB_PATH 或显式要求传入）。

### R7-A1-08（L-036）config.py
现状：load_env 只 strip 不剥行内注释，用户自写 env 带 # 会静默错解析。
期望：解析时剥行内注释（注意 # 在值内的边界），与 .env.example 已清理的模板一致。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall novel_editorial/web_api.py novel_editorial/services/misc.py novel_editorial/db.py novel_editorial/services/control.py novel_editorial/config.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
