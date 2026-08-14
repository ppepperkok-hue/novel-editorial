# 通用规则（Common Rules）

本文档只定技术约定；行为规则（验证纪律、失败显式化、配置驱动、幂等、最小改动、文档如实、审查义务、权限边界、沟通纪律、冲突规则）见 Agent 宪法（04 步产出）。

## 1. 目录与命名

- 采用 src 布局：`src/novel_editorial/` 为包根，`tests/` 镜像包结构。
- 模块小写下划线；类用 PascalCase；常量用 UPPER_SNAKE。
- 分层目录约定：`cli/`（命令入口）、`core/`（领域模型与服务）、`store/`（数据访问）、`llm/`（LLM 客户端）、`quality/`（质量门）、`events.py`（事件契约）。
- 每部作品数据放 `data/works/<workspace_id>/`，全局库放 `data/global.db`；配置放 `config.toml`（用户级可覆盖）。

## 2. 依赖方向

- `cli → core → store/llm/quality`；`events` 为共享契约层，任何模块可读。
- 禁止反向依赖（core 不得 import cli）；禁止循环依赖。
- 检查手段：pytest 依赖方向守卫测试 + 人工 review；ruff 负责基本规范。

## 3. 错误处理与日志

- 自定义异常基类 `NovelError`，携带错误码（`NOVEL_*` 枚举）与上下文；业务异常可预测，系统异常不吞。
- 日志分级：系统日志走 stderr（运行与错误），创作日志走数据库（业务事实），两者分离。
- 静默吞错是红线（行为规则见 04 宪法）。

## 4. 配置与密钥

- 环境变量统一前缀 `NOVEL_`；敏感值（LLM API key）只从环境变量或 `.env` 读取，绝不落库、绝不进仓库。
- 提供 `.env.example` 模板；`config.toml` 存非敏感默认与用户偏好。
- 硬编码敏感值或路径是红线。

## 5. 接口契约

- CLI 命令命名：动词-宾语（`works create`、`draft submit`、`decision accept`）。
- 事件契约：统一结构 `{type, time, actor, workspace, payload}`，类型枚举见 `events.py`；Pydantic 模型校验。
- 错误码枚举集中定义；命令退出码：0 成功、1 业务错误、2 用法错误、3 系统错误。

## 6. 测试规则

- 布局：`tests/` 镜像 `src/`；文件名 `test_*.py`；一个单元至少一个测试。
- 核心服务层行覆盖率 ≥ 80%（M1 结束时统计）；LLM 用模拟模式测试，错误路径必须测。
- 验证命令（本地与 CI 同一套）：
  - `uv run pytest -q -n auto`（全量并行；子集用 `-m smoke`，重跑失败用 `--lf`）
  - `uv run ruff check`
  - `uv run pyright`
  - `uv run novel-editorial --version`

## 7. 代码风格与提交

- 代码格式：ruff format（行宽 100）。
- 提交信息：Conventional Commits，英文（`feat:` / `fix:` / `docs:` / `test:` / `chore:`）。
- 提交前必须通过全部验证命令；文档变更与代码同提交。
