# 修复任务包 · R8-B2 链路展示

你是严格的修复工程师。仓库：`E:\code\novel-editorial`。本轮为第八轮审查修复（遗留跟进）。第七轮总结遗留节：`docs/reviews/rounds/20260812-round7/00-summary.md`。

## 只允许修改的文件（禁止改其他任何文件，禁止 git add/commit，禁止清理未指派文件）

- `tools/export_flow_html.py`
- `tools/flow_graph.py`

## 修复项

### R8-B2-01（遗留）export_flow_html.py / flow_graph.py
现状：整轮失败时链路图给所有节点上 bad/failed 样式，而不是只标失败节点。
期望：评估展示口径：只标实际失败节点（按 daily_runs.failed_nodes），其余节点保持运行/待命；如果 current 数据无法区分，至少文档化说明并给出明确降级。

## 纪律

- 最小聚焦 patch，不重写无关代码，不格式化无关文件。
- 验证：`python -m compileall tools/export_flow_html.py tools/flow_graph.py`；用 rg 找相关测试并 pytest 运行。
- 完成后用中文报告：修复的文件+行号+改动摘要+验证结果，以及发现的额外问题（只报告不改）。
