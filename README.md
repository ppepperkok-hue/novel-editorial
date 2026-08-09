# novel-pipeline

AI 网文自动生成与发布流水线：n8n 定时编排 + DeepSeek 写作 + Python 记忆层 + 番茄小说发布 + 实时监控面板。

## 特性

- 每日定时自动生成两章并提交番茄审核（`new_article → cover_article → publish_article`）
- 长篇连贯性：故事圣经冻结、10 章蓝图、写前记忆包（上一章结尾 / 章节摘要 / 角色状态 / 伏笔 / 标题查重）、写后结构化沉淀
- 写作质量体系：黄金三章、爽点密度、四类章末钩子、「起承转爽」节奏模板、反 AI 高频词黑名单（见 `prompts/writing_techniques.md`）
- 自动填写书名 / 简介 / 标签 / 主角名（`modify_book`），章节号动态续接
- 零依赖监控面板：作品库（大纲 / 主角 / 标签 / 蓝图）、章节、发布日志、完读率导入位
- 正文分段兜底：模型不给换行时按句读自动断段

## 快速开始

```bash
# 安装依赖
pip install -e .

# 启动监控面板（浏览器打开 http://127.0.0.1:8000/）
python -m novel_pipeline.web_api --db demo.db --port 8000

# 生成演示数据（可选）
python -m novel_pipeline.seed_demo --db demo.db

# 运行测试
python run_tests.py
```

## 目录结构

```text
novel_pipeline/   Python 库：db / web_api / monitor / data_feedback / planner / publisher ...
web/              监控前端（5 秒轮询 /api/dashboard）
prompts/          提示词资产：writer / reviewer / editor / memory / writing_techniques
tools/            运维脚本（get_meta / record_work / paragraphs / n8n_api ...）
docs/             架构文档与调研资料
n8n/              n8n 工作流 JSON 与运维说明
demo_data/        样例数据
tests/            自动化测试
```

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## n8n 工作流

工作流文件：`n8n/novel_workflow.json`，导入后配置：

- 环境变量（`~/.n8n/.env`）：`DEEPSEEK_API_KEY`、`FANQIE_COOKIE`、`FANQIE_CSRF_TOKEN`
- 每日 08:00 自动执行；`n8n/README.md` 记录了完整的番茄发书流程、已知限制与运维要点

## 安全说明

- 所有凭据（DeepSeek Key、番茄 Cookie、n8n 登录）都走环境变量，仓库内不存任何密钥
- 本地数据库 `demo.db`、备份与第三方参考代码不随仓库发布（见 `.gitignore`）
