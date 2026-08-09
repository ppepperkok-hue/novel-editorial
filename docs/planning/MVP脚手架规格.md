# MVP 脚手架规格（Phase 1 前置设计）

> 本规格与具体技术路线无关：n8n、OpenNovel（LangGraph）、从零实现均可映射到同一套模块。决策「平台 + 预算 + 技术路线」后即可按此开工。

---

## 1. 数据模型（SQLite）

```text
novels          id, title, genre, premise, selling_point, target_words,
                update_schedule, platform, status
volumes         id, novel_id, seq, goal, outline
chapters        id, novel_id, volume_id, seq, outline,
                status(draft/edited/reviewed/queued/published/failed),
                words, score, published_at
characters      id, novel_id, name, role, traits, goals,
                state(JSON，每章后更新), first_seen_chapter
world_events    id, novel_id, chapter_id, event, impact
plot_threads    id, novel_id, planted_chapter, expected_recover_chapter, status
quality_reports id, chapter_id, scores(JSON), passed, revision_count
publish_logs    id, chapter_id, platform, action, result, error, ai_declared
```

---

## 2. Agent 角色与职责

| Agent | 职责 |
|---|---|
| ResearchAgent | 榜单/题材调研 → 选题卡片 |
| ArchitectAgent | 立项：世界观、金手指、卖点、目标字数 |
| PlannerAgent | 卷纲 / 章纲 / 伏笔表 |
| WriterAgent | 按章纲 + 检索上下文写初稿 |
| EditorAgent | 润色、调字数、去 AI 味 |
| ReviewerAgent | 五维评分，决定通过 / 重写 |
| MemoryAgent | 每章摘要、角色状态、世界事件更新；每 5 章全局一致性审查 |
| PublisherAgent | 平台适配 + 定时调度 + 发布日志 |
| MonitorAgent | 告警：发布失败 / 审核驳回 / Cookie 失效 / 断更 / 成本超限 |

---

## 3. 质量门评分表

每维 0-10 分，**总分 ≥ 7 且单维 ≥ 5 才通过**；未通过最多重写 3 次，仍不达标则标记人工介入。

| 维度 | 检查点 |
|---|---|
| 字数 | 目标区间 ±10% |
| 情节 | 紧扣章纲，有钩子、有推进、有爽点 |
| 文笔 | 句式变化、对话自然、无程式化表达 |
| AI 痕迹 | 模板词频率、检测工具得分 |
| 规范衔接 | 全角标点、对话引号规范、与前章无矛盾 |

---

## 4. 合规门 Checklist（每章发布前）

- [ ] 目标平台规则清单已加载
- [ ] 敏感词扫描通过
- [ ] AI 声明状态已记录并随发布提交
- [ ] 字数与格式符合平台要求
- [ ] 发布日志可追溯

---

## 5. 发布适配器接口

```python
class PublisherAdapter:
    def list_books(self): ...
    def switch_book(self, book_id): ...
    def list_chapters(self): ...
    def publish(self, chapter, scheduled_at=None, as_draft=False): ...
```

| 适配器 | 实现 |
|---|---|
| FanqieHttpAdapter | Cookie + CSRF 直接调作者后台接口（推荐，支持定时发布） |
| FanqieBrowserAdapter | Playwright 兜底通道 |
| QidianAdapter | 生成稿件 + 发布提醒，发布动作走官方客户端定时发布 |
| ManualAdapter | 输出待发布清单，人工确认后发布 |

---

## 6. 调度与存稿池

- 存稿池：提前备 3-5 章；低于安全线触发断更预警。
- 调度：优先平台侧定时发布（服务端执行、最稳）；本地 APScheduler / n8n 定时兜底。
- 健康检查：每日检查发布队列、Cookie 有效期、月度成本用量。

---

## 7. 成本估算（单章约 2000-2300 字，含生成 + 润色 + 审稿 + 上下文）

| 档位 | 示例模型 | 单章估算 | 月成本（日更 2 章） |
|---|---|---|---|
| 入门 | DeepSeek V3 / R1 系列 | ¥0.1-0.5 | ¥6-30 |
| 中档 | Claude Sonnet 级 / GPT 中档 | ¥1-4 | ¥60-240 |
| 旗舰 | Claude Opus 级 | ¥10-30 | ¥600-1800 |

> 实测参考：有作者用 DeepSeek 写约 2000 字章节约消耗 46k tokens，折合约 ¥0.11（2026-02）。最终以模型定价为准；开启缓存与批处理可进一步降低成本。

---

## 8. 技术路线映射

- **n8n（推荐给非程序员）**：每个模块一个子工作流；用 MemMachine 节点做持久记忆；HTTP Request 节点接番茄接口；定时触发器调度；Webhook 接告警。
- **OpenNovel（LangGraph，推荐给能写代码的人）**：直接复用其 agents / workflow / memory / publisher 结构，替换模型与平台适配器即可。
- **从零实现**：按本规格实现，推荐 Python + LangGraph 或裸函数流水线。

---

## 9. Phase 1 验收标准

- 连续 10-20 章过质量门，通过率 ≥ 95%
- 平台审核过审率 100%
- 单章人工耗时 < 15 分钟
- 记录读者数据基线（完读率 / 追读率），供 Phase 3 对比

---

## 10. 实时监控与热点选题（新增模块）

| 模块 | 职责 |
|---|---|
| `web_api.py` | 零依赖 Web 服务：`/api/dashboard` 一次拉全汇总、小说、章节、发布日志、健康检查、阅读数据、热点 |
| `web/index.html` | 纯静态监控面板，每 5 秒轮询，无构建步骤 |
| `hot_topics.py` | 抓取公开网文榜单（起点/番茄），提取书名与题材关键词；CSV 兜底 |

- 监控数据来源：SQLite + `alerts.log` + `hot_topics.json` + 阅读数据 CSV。
- 热点结果可直接喂给 Planner 做选题候选；抓取失败不阻塞流水线。
