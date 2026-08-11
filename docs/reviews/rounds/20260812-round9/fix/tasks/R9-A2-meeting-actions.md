# 修复任务包 · R9-A2 会议幂等与链路别名

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第九轮审查修复（第八轮遗留跟进）。第八轮总结遗留节：`docs/reviews/rounds/20260812-round8/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/meeting_actions.py`
- `tools/flow_graph.py`

## 修复项

### R9-A2-01（遗留）meeting_actions.py
现状：run_post_actions 幂等「先查后插」，并发双跑可能重复应用；需唯一约束或条件插入根治。
期望：audit_logs 相关列加唯一索引（幂等迁移），或把标记插入改为条件 INSERT，并发下只应用一次。

### R9-A2-02（遗留）flow_graph.py
现状：FAILED_ALIAS 未映射 legacy n8n 名字（如「预检」「未知节点」），该类失败无法高亮。
期望：FAILED_ALIAS 增加 legacy 名字映射（如 预检/preflight/未知节点/unknown）。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 修 bug 时，能写失败测试就先写（测试文件不在指派范围时，在最终结果中列出测试建议，不改测试文件）。
- 验证：`python -m compileall tools/meeting_actions.py tools/flow_graph.py`；用 rg 找相关测试并 pytest 运行；并发重复应用用双线程实测。
- 完成后用中文报告：每项修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
