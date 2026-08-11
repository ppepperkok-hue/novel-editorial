# 修复任务包 · R6-B 编辑部链路

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第六轮分片审查修复，审查报告：`docs/reviews/rounds/20260812-round6/slices/slices-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/relations.py`
- `tools/editorial_daily.py`
- `tools/daily_runs.py`
- `tools/agent_meeting.py`
- `tools/editorial_state.py`

## 修复项

### R6-B-01（P1）relations.py:44-49
现状：ensure 在迁移库上必现 NOT NULL IntegrityError，导致日更整体失败。
期望：对迁移库/缺失列做兼容（如按表结构动态插入或先建列），日更不被阻塞；失败显式留痕。

### R6-B-02（P2）editorial_daily.py:97-98
现状：_handle_outbox 对 LLM 输出做无防护 int() 转换，非数字 reply_to 会拖垮整次日更。
期望：int() 容错（失败按无回复处理并留痕），不中断整批。

### R6-B-03（P2）editorial_daily.py:1656-1660
现状：daily() skipped 分支无条件删除 daily_runs 行，会删掉 workday 创建的工作日记录。
期望：只删除本批次自建的运行记录；workday 来源的行保留并正确标记 skipped。

### R6-B-04（P3）daily_runs.py:56-70
现状：sync_from_n8n 无异常防护，n8n 本地库不可读时 executions 端点 500。
期望：捕获异常返回空列表/错误标记，不 500。

### R6-B-05（P3）agent_meeting.py:748-753
现状：apply_report 只捕获 ImportError/AttributeError，outline 损坏时会议 CLI 崩溃。
期望：对 JSON/形状错误统一容错（默认结构 + 留痕），不崩溃。

### R6-B-06（P3）editorial_state.py:11-13
现状：_scoped_ids 的 (0,) 分支不可达（死代码）。
期望：确认后删除死分支或修正逻辑。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/relations.py tools/editorial_daily.py tools/daily_runs.py tools/agent_meeting.py tools/editorial_state.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
