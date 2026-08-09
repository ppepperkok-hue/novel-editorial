# 项目架构

## 目录结构

```text
novel-pipeline/
├── novel_pipeline/          # Python 库：db / web_api / monitor / data_feedback / planner / publisher ...
├── web/                     # 监控前端（index.html，5 秒轮询 /api/dashboard）
├── prompts/                 # 提示词资产：writer / reviewer / editor / memory / writing_techniques
├── tools/                   # 运维脚本（n8n Execute Command 与手动运维均指向这里）
│   └── archive/             # 历史补丁与一次性脚本（保留备查）
├── docs/research/           # 调研资料：GitHub 参考项目、写作技巧原始文档
├── n8n/                     # n8n 工作流 JSON + 运维说明 README
├── demo_data/               # 样例数据（reader_stats.example.csv 等）
├── demo.db                  # SQLite 数据库（作品/章节/角色/摘要/伏笔/发布日志）
├── hot_topics.json          # 热点选题缓存
├── run_tests.py / pyproject.toml
└── README.md
```

## 数据流

```text
n8n 每日 08:00
  → 查章节号（番茄 book_list）
  → 读本地资料 tools/get_meta.py（记忆包：故事圣经/蓝图/摘要/角色状态/伏笔/已有标题）
  → 生成作品资料（DeepSeek，仅默认书名时提交修改）
  → 生成两章章纲（Planner，带钩子类型/节奏标注）
  → 写手A/B（记忆包 + 章纲 + 网文节奏与去AI味规则）
  → 润色/审稿/质量门（连贯性 + 爽点 + AI 词检查）
  → 发布番茄（new_article → cover_article → publish_article）
  → 记录入库 tools/record_work.py（章节/摘要/角色状态/事件/伏笔 → demo.db）
  → 前端 web_api 展示作品库（书名/简介/标签/主角/大纲/蓝图/章节/发布日志）
```

## 关键脚本

- `tools/get_meta.py`：组装记忆包，供写前上下文使用
- `tools/record_work.py`：运行结果入库（含章节摘要与角色状态沉淀）
- `tools/paragraphs.py`：正文分段兜底（无换行时按句读自动断段）
- `tools/rewrite_book.py` / `refix_chapters.py`：整书重写 / 章节重发
- `tools/n8n_api.py`：n8n 工作流管理（登录/更新/运行/查询执行）

## 记忆与连贯性

参考 OpenNovel / long-novel-writer / AI Fiction Studio 设计：
故事圣经冻结 → 10 章蓝图 → 写前记忆包 → 写后结构化沉淀 → 连贯性专审。
详见 `prompts/writing_techniques.md` 与 `docs/research/`。
