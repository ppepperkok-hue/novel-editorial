# 项目架构

## 目录结构

```text
novel-pipeline/
├── novel_pipeline/          # Python 库
│   ├── config.py            # 集中配置：路径 / env 加载 / 常量
│   ├── db.py                # SQLite 数据层与迁移
│   ├── llm_client.py        # 统一 LLM 客户端（DeepSeek 直连 + 旧兼容类）
│   ├── web_api.py           # HTTP 路由壳（业务在 services/）
│   ├── services/            # 服务层：n8n / control / dashboard / agents / ending / misc
│   ├── monitor.py / data_feedback.py / publisher.py ...  # 领域逻辑
│   └── desktop.py           # pywebview 后备桌面入口
├── prompts/agents/          # 11 个人格化 Agent（人物档案 + 日常/日记/周记/会议模式）
├── tools/                   # 流水线脚本
│   ├── render_workflow.py / export_agent_prompts.py   # Agent 资产 ↔ 工作流
│   ├── preflight.py / publish_stock.py / check_stock.py  # 日更控制
│   ├── agent_meeting.py / write_diaries.py / architect_weekly.py / apply_architect.py  # 周会系统
│   ├── ai_taste_check.py / get_meta.py / record_work.py / collect_reader_stats.py ...
│   └── debug/               # 一次性调试/探索脚本（probe_*、cdp_*、query_* 等）
├── webapp/                  # React + Vite 前端（Electron 桌面壳加载）
├── desktop/                 # Electron 壳（main/preload/release.js）
├── n8n/                     # n8n 工作流 JSON（日更 61 节点 / 周会 7 节点 / 知识管家 4 节点）
├── docs/                    # evolution / planning / research
├── tests/                   # 136 个后端测试 + 前端 Vitest
└── demo.db / exports / n8n_tmp / backups  # 运行数据
```

## 数据流

```text
n8n 每日 08:00 或 Webhook 手动补更
  → 查章节号（番茄 book_list）
  → 读本地资料 tools/get_meta.py（记忆包：故事圣经/蓝图/摘要/角色状态/伏笔/已有标题）
  → 生成作品资料（DeepSeek，仅默认书名时提交修改）
  → 生成两章章纲（Planner，带钩子类型/节奏标注）
  → 写手A/B（记忆包 + 章纲 + 去 AI 味/辞藻平实规则）
  → 润色/审稿/质量门（AI 词表来自共享 ai_words.json；质量门失败显式落库 draft+error）
  → 直发成功章节落库 status=published、发布失败保留 reviewed 供补发
  → tools/publish_stock.py 按「每批发布章数」从存稿池发布番茄（存稿优先）
  → 两条路径汇入收尾：采集阅读数据 → 全员写日记 → 同步设定知识库 → 结束
  → 前端 web_api（services 层）展示作品库/章节/成本/执行/阅读数据

n8n 每周日 08:10（或手动）
  → tools/agent_meeting.py 多 Agent 会议：
     全员写周记（含心情）→ 主席点将 → 3 轮通气 → 主席总结报告
  → weekly_meetings 存档；蓝图/卷目标落盘供日更消费
```

## 关键脚本

- `tools/get_meta.py`：组装记忆包，供写前上下文使用
- `tools/record_work.py`：运行结果入库（含章节摘要与角色状态沉淀）
- `tools/publish_stock.py`：存稿池发布 + 收尾章数递减
- `tools/agent_meeting.py` / `tools/write_diaries.py`：多 Agent 会议与两级记忆
- `tools/ai_taste_check.py`：AI 味检测（华丽辞藻/填充词/密度评分）
- `tools/preflight.py`：日更预检（Cookie/预算/幂等/并发锁）
- `novel_pipeline/llm_client.py`：统一 DeepSeek 客户端
- `tools/debug/`：一次性调试脚本（probe_*/cdp_*/query_* 等）

## 记忆与连贯性

参考 OpenNovel / long-novel-writer / AI Fiction Studio 设计：
故事圣经冻结 → 10 章蓝图 → 写前记忆包 → 写后结构化沉淀 → 连贯性专审。
详见 `prompts/writing_techniques.md` 与 `docs/research/`。
