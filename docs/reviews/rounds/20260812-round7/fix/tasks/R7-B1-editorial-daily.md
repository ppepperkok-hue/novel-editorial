# 修复任务包 · R7-B1 日更与工具

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第七轮审查修复（新发现 + 遗留跟进）。审查报告：`docs/reviews/rounds/20260812-round7/slices/slices-summary.md`；遗留跟踪表：`docs/reviews/rounds/legacy-tracker.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/editorial_daily.py`
- `tools/workday.py`
- `tools/architect_weekly.py`
- `tools/auto_fill_actions.py`
- `tools/write_diaries.py`
- `tools/ai_taste_check.py`

## 修复项

### R7-B1-01（P2，新）auto_fill_actions.py
现状：publish_logs 证据未按 novel 过滤，跨书误标行动项为 done。
期望：按 novel_id 过滤证据，跨书不误标。

### R7-B1-02（P2，新）write_diaries.py
现状：write() 无单 agent 失败隔离，一次 LLM 失败中断全部日记与周会。
期望：单 agent 失败隔离（跳过并留痕），其余 agent 日记照常写。

### R7-B1-03（L-006）editorial_daily.py
现状：_preflight dry-run 下仍写 audit_logs。
期望：dry-run 全路径无持久化副作用（参考 workday 已修模式）。

### R7-B1-04（L-030）editorial_daily.py
现状：_review_tone 等查询硬编码 other=?，旧迁移数据未回填 other 时漏匹配。
期望：兼容 other/other_agent 两列（参考 relations.ensure 的迁移兼容模式）。

### R7-B1-05（L-024）workday.py
现状：main() 业务失败时 CLI 仍 exit 0。
期望：业务失败返回非 0 退出码（如 sys.exit(main()) 模式）。

### R7-B1-06（L-007）architect_weekly.py
现状：tags 裸 json.loads、settings int() 无兜底。
期望：解析容错（默认值 + 留痕），不中断周会。

### R7-B1-07（L-011）ai_taste_check.py
现状：detect 返回的明细 map 仍逐词重叠计数，与内部非重叠密度并存，消费方可能误判。
期望：明细 map 与密度计数口径统一（非重叠），或明确标注明细为原始命中。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/editorial_daily.py tools/workday.py tools/architect_weekly.py tools/auto_fill_actions.py tools/write_diaries.py tools/ai_taste_check.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
