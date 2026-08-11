# 标准审查流程（Review Process）

> 从 2026-08-11 起，所有审查（前端 / 后端 / 工作流 / 数据链路）统一按
> 本流程执行。任何一轮"再审查一遍"都必须产出可复现的审查记录，
> 报告落 `docs/reviews/`，并附验证命令与证据。

## 1. 原则

- **证据优先**：每条结论必须带证据（文件:行号 / API 响应 / 测试输出），
  不允许"感觉有问题"。
- **字段对照**：前端读取的每个字段都要在后端接口里找到出处；
  后端返回的每个字段都要有消费方（没有消费方 = 死数据）。
- **动作对照**：每个按钮/表单提交都要追到后端实现；后端实现必须真实存在
  且被调用（不允许只弹 Toast 不做事）。
- **分级明确**：P0 数据损坏/丢钱/无法运行；P1 影响真实使用；
  P2 展示错误/不一致/死模块；P3 小问题/体验。
- **可复现**：报告里的验证命令任何人可重跑，结果一致。

## 2. 审查范围（按需裁剪）

### 2.1 前端（webapp）

逐组件检查：

- 数据源：组件里每个 `getXxx`/`postXxx` 是否在 `api.js` 存在，
  API 端点是否在 `web_api.py` 实现，返回字段与组件解构是否一致。
- 动作链：按钮 → API → 后端 handler → 副作用（写库/触发工作流）是否完整；
  操作后是否刷新相关状态。
- 状态三态：空态 / 加载态 / 错误态是否都有合理 UI。
- 时间与时区：`toISOString()`（UTC）与后端本地时间字符串混用会错位；
  所有"今日/本周"统计必须用本地日期。
- 硬编码一致性：节点数、上限、文案中出现的数字，必须与后端/工作流实际
  值一致（例如"60 节点"vs 实际 65 节点）。
- 死模块：有条件渲染的区块，其数据源字段必须真实存在于后端返回；
  不存在则标记"无数据源"，建议删除或接数据。
- 实时通道：SSE 快照是否覆盖/截断轮询数据（例如 executions 被截成 5 条）。
- Electron 集成：`preload.js` 暴露的每个方法在 `main.js` 是否有
  `ipcMain` 对应；`desktopApi` 调用是否有 try/catch。
- 测试覆盖：Vitest 是否覆盖核心交互；新模块必须有测试。

### 2.2 后端（novel_pipeline / tools）

- 每个 API handler 的输入校验、错误返回（HTTP 码 + JSON body）。
- 数据库写入是否幂等/防重复；空载荷是否有防护。
- 与工作流的衔接（executeCommand / httpRequest 的参数与字段）。
- 锁与并发（日更锁、会议锁）是否有死锁/残留风险。

### 2.3 工作流（n8n JSON）

- `node tools/validate_workflow_deep.mjs` 必须通过。
- 拓扑走查：每个分支（main/error）终点是否可达"结束/释放锁"。
- 节点数据流：上游输出字段与下游表达式引用是否一致
  （例如排版节点必须从润色节点取正文，而不是从摘要节点）。

### 2.4 数据链路（端到端）

- 关键操作实跑一次：开会 → 建书 → 日更 → 发布 → 落库 → 日记 → 释放锁。
- 用 `scripts/watch_daily.py` 观察执行；用番茄侧接口复核发布结果。

## 3. 标准验证命令

```bash
# 后端
cd E:\code\novel-pipeline
python run_tests.py
node tools/validate_workflow_deep.mjs

# 前端
cd webapp
npm test
npm run build

# API 抽查（字段对照）
python - <<'PY'
import json, urllib.request
def get(p):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:8000"+p, timeout=15).read())
for p in ["/api/dashboard","/api/control","/api/agents","/api/cost",
          "/api/executions","/api/meetings","/api/activity","/api/agent_actions"]:
    print(p, sorted(get(p).keys()))
PY
```

## 4. 报告模板（docs/reviews/YYYYMMDD-<scope>-review.md）

```markdown
# <范围>审查报告（YYYY-MM-DD）

## 审查范围与方法
（列组件/接口清单 + 用了哪些验证命令）

## 总评
（3-5 句：骨架是否健康、有无摆设、最值得修什么）

## 问题清单
（P0/P1/P2/P3 分级；每条含：证据 文件:行号 或 API 响应、影响、建议）

## 确认无问题的模块
（逐个模块说明为什么可用，防止下次重复审查）

## 验证记录
（实际执行的命令与输出摘要；测试数、构建结果、API 抽查结果）

## 后续建议
（修复优先级、需要补的测试、需要删除的死模块）
```

## 5. 严重程度定义

| 级别 | 含义 | 例子 |
| --- | --- | --- |
| P0 | 数据损坏 / 丢钱 / 无法运行 | 发布空章、覆盖真实数据、数据库损坏 |
| P1 | 影响真实使用 | 列表被截断、日期统计错、动作无效 |
| P2 | 展示错误 / 不一致 / 死模块 | 节点数写死、上限不一致、无数据源区块 |
| P3 | 小问题 / 体验 | 缺失筛选、文案、快捷键、性能 |

## 6. 审查记录索引

- 2026-08-11 前端全量审查：`docs/reviews/20260811-frontend-review.md`

