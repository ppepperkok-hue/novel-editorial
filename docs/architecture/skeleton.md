# 最小骨架（Minimal Skeleton）

## 目录结构

```text
novel-editorial/
├── src/novel_editorial/
│   ├── __init__.py          # 包元信息（__version__）
│   ├── __main__.py          # python -m novel_editorial 入口
│   ├── events.py            # 共享事件契约（EventType / Event）
│   ├── cli/                 # CLI 命令层（Typer）
│   │   ├── __init__.py      # CLI 包入口
│   │   ├── app.py           # 主入口：init / health / version / demo / log / inspect + 命令组挂载
│   │   ├── works.py         # works 命令组
│   │   ├── agents.py        # agents 命令组
│   │   ├── talk.py          # talk 命令组
│   │   ├── style.py         # style 命令组
│   │   ├── memory.py        # memory 命令组
│   │   ├── draft.py         # draft 命令组
│   │   ├── review.py        # review 命令组
│   │   ├── decision.py      # decision 命令组
│   │   ├── quality.py       # quality 命令组
│   │   ├── plot.py          # plot 命令组
│   │   └── events.py        # events 命令组
│   ├── core/                # 领域基础层
│   │   ├── config.py        # 配置加载（NOVEL_* 环境变量 + config.toml）
│   │   ├── errors.py        # NovelError 错误体系与错误码
│   │   ├── memory.py        # 伙伴私有记忆服务（U18）
│   │   └── logging_setup.py # 系统日志（stderr）
│   ├── store/               # 数据访问层
│   │   ├── db.py            # 全局库 + 每作品库引擎管理
│   │   └── models.py        # SQLAlchemy 模型（Workspace / Agent / AgentMemory）
│   ├── llm/                 # LLM 客户端层（U5 完善）
│   │   └── client.py        # LLMClient 协议 + MockLLMClient
│   └── quality/             # 质量门层（U13 完善）
│       └── gate.py          # 占位质量门
├── tests/                   # pytest（镜像 src 结构）
├── pyproject.toml           # 依赖与工具配置（uv 管理）
├── .env.example             # 环境变量模板
└── .gitignore
```

## 数据布局

- 全局库：`data/global.db`（作品注册表 Workspace）。
- 作品库：`data/works/<workspace_id>/data.db`（该作品的班子 Agent、后续草稿 / 日志等）。
- 配置：`config.toml`（非敏感默认）；敏感值只走环境变量（`NOVEL_*`）。
- Schema 单一权威来源：Alembic 迁移（`alembic.ini` + `migrations/`）；`init` 与作品创建均走 `alembic upgrade head`，不再使用 `create_all`。

## 启动方式

```bash
uv run novel-editorial init          # 初始化数据目录与配置
uv run novel-editorial health        # 健康检查（配置 + 数据库）
uv run novel-editorial --version     # 版本
uv run novel-editorial works create "书名" --genre "体裁"
uv run novel-editorial works list
```

## 验证命令（本地与 CI 同一套）

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run novel-editorial --version
```

## 已验证状态

- `pytest`：10 passed（版本、`--version` 选项、配置、作品创建 / 列表 / 详情、默认班子、业务错误退出码、依赖方向守卫）。
- `ruff check .`：0 错误。
- `pyright`：0 错误。
- CLI 冒烟：`--version`、`health`、`works create`、`works list`、`works show` 全部跑通，中文输出正常；业务错误输出友好信息并返回退出码 1。
- 最小链路：命令 → 业务（创建作品 + 默认班子）→ 存储（全局库 + 作品库）→ 响应，真实跑通。
