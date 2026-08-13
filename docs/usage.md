# 使用文档：配置与常见问题

面向用户的配置说明与 FAQ，命令与输出以当前实现（0.1.0）为准。

## 配置总览

程序每条命令运行时读取两部分配置：

1. 环境变量 `NOVEL_*`（敏感信息如 API key 只放这里）
2. 本地 `config.toml`（非敏感默认值与偏好）

优先级：环境变量 > `config.toml` > 内置默认值。`novel-editorial init` 会自动生成 `config.toml`（模板见仓库根目录的 `config.example.toml`）。

## config.toml

目前支持的配置段是 `[defaults]`：

```toml
[defaults]
quality_threshold = 8
```

- `quality_threshold`：质量门阈值（整数），默认 `8`；草稿得分 ≤ 阈值才算通过。
- 仓库里的 `config.example.toml` 只写了空的 `[defaults]` 段头，把上面的键补进你自己生成的 `config.toml` 即可。
- 每次运行命令都会重新读取，改完无需重启任何服务。

## NOVEL_* 环境变量

| 变量 | 作用 | 默认值 | 示例 |
| --- | --- | --- | --- |
| `NOVEL_DATA_DIR` | 数据目录 | `./data` | `D:\novels\data` |
| `NOVEL_CONFIG` | 配置文件路径 | `./config.toml` | `./my-config.toml` |
| `NOVEL_LLM_API_KEY` | LLM 密钥；留空即用 mock | 空 | `sk-...` |
| `NOVEL_LLM_BASE_URL` | OpenAI 兼容接口地址 | `https://api.deepseek.com` | `https://api.openai.com/v1` |
| `NOVEL_LLM_MODEL` | 模型名 | `deepseek-chat` | `gpt-4o-mini` |
| `NOVEL_LOG_LEVEL` | 日志级别（输出到 stderr） | `INFO` | `DEBUG` |
| `NOVEL_QUALITY_THRESHOLD` | 质量门阈值 | `config.toml` 的 `quality_threshold`，再退到 `8` | `6` |

阈值优先级：`NOVEL_QUALITY_THRESHOLD` > `config.toml [defaults].quality_threshold` > 内置默认 `8`。

仓库里的 `.env.example` 模板列了 `NOVEL_LLM_API_KEY`、`NOVEL_LLM_BASE_URL`、`NOVEL_LLM_MODEL`、`NOVEL_DATA_DIR`、`NOVEL_LOG_LEVEL`；本表另外补充的 `NOVEL_CONFIG` 与 `NOVEL_QUALITY_THRESHOLD` 同样受支持。

Windows PowerShell 示例：

```powershell
$env:NOVEL_LLM_API_KEY = "sk-..."
$env:NOVEL_LLM_BASE_URL = "https://api.openai.com/v1"
$env:NOVEL_LLM_MODEL = "gpt-4o-mini"
```

bash / zsh 示例：

```bash
export NOVEL_LLM_API_KEY="sk-..."
export NOVEL_LLM_BASE_URL="https://api.openai.com/v1"
export NOVEL_LLM_MODEL="gpt-4o-mini"
```

### .env 的用法

程序**不会自动加载 `.env` 文件**。仓库里的 `.env.example` 只是模板：复制成 `.env` 后，需要由你的 shell 把内容读入环境变量。

bash / zsh：

```bash
set -a
source .env
set +a
```

PowerShell：

```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
    [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
  }
}
```

或者干脆不用 `.env`，直接 `export` / `$env:` 设置。

## 换 LLM 供应商

程序走 OpenAI 兼容的 chat completions 接口，默认指向 DeepSeek：

```bash
export NOVEL_LLM_API_KEY="你的 DeepSeek key"
# BASE_URL 与 MODEL 不设置时即 https://api.deepseek.com + deepseek-chat
```

换 OpenAI：

```bash
export NOVEL_LLM_API_KEY="sk-..."
export NOVEL_LLM_BASE_URL="https://api.openai.com/v1"
export NOVEL_LLM_MODEL="gpt-4o-mini"
```

其他 OpenAI 兼容供应商（含本地推理服务）只要提供 `/chat/completions` 风格接口，改这三个变量即可。

## 质量门

- 得分公式：AI 味词命中数 × 6 + 修饰词命中数 × 3 + 句式重复数 × 4 + 风格一致性罚分（缺失风格关键词的比例 × 0.5）。
- 通过条件：得分 ≤ 阈值（默认 `8`）；得分越低越「干净」。
- `draft generate` / `draft revise` 会自动跑门：没过 → 草稿状态 `quality_failed`，此时 `decision accept` 会被拒绝（可 `decision reject` 或修订后重试）。
- 查看详情与定位：

```bash
uv run novel-editorial quality check <草稿ID>
uv run novel-editorial quality explain <草稿ID>
```

`check` 输出通过与否、得分与各维度命中；`explain` 逐句定位并给出改写建议（无问题时输出「未发现明显 AI 味」）。

- 调整阈值：`NOVEL_QUALITY_THRESHOLD=6`（更严）或在 `config.toml` 里写 `quality_threshold = 6`。阈值非整数会报配置错误（退出码 1）。

## 数据目录与备份

- `NOVEL_DATA_DIR`（默认 `./data`）：
  - `global.db`：作品注册表；
  - `works/<作品ID>/data.db`：该作品的对话、草稿、意见、决策、私有记忆、叙事线索等，每部作品一个独立库。
- 表结构由 Alembic 迁移自动维护，升级代码后首次运行会自动应用迁移。
- 备份：直接复制 `NOVEL_DATA_DIR` 整个目录；恢复时放回原位并让 `NOVEL_DATA_DIR` 指向它。
- 仓库根目录的 `novel-editorial-backup-*.zip` 只是仓库备份用途，与运行时数据无关。

## 私有记忆的权限规则

- 作者是只读的：`memory note` 不写 `--as`（默认作者）会被拒绝，报「作者只读，请用 --as <伙伴别名> 以伙伴身份写入」。
- 伙伴只能写自己的笔记：`--as 写手` 只能写给写手，写给别人会报错。
- `--as` 只用于权限校验，不会落库；笔记归属由目标伙伴决定。

```bash
# 正确：以写手身份写给写手
uv run novel-editorial memory note <作品ID> 写手 --content 主角害怕旧车站的钟声 --as 写手

# 看某人的笔记 / 看所有人的笔记
uv run novel-editorial memory notes <作品ID> 写手
uv run novel-editorial memory notes <作品ID>

# 删除某条笔记（用 notes 输出里的 id）
uv run novel-editorial memory delete <作品ID> <笔记ID>
```

写手的笔记会进入 `memory pack` 的「私有记忆」段，创作时注入给写手本人。

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | 业务错误（找不到对象、配置错误、LLM 调用失败等） |
| `2` | 用法错误（参数错误、状态机冲突如重复拍板 / 修订已接受草稿） |
| `3` | 未预期的系统错误 |

## 常见问题（FAQ）

### 不配 key 能跑吗？

能。没有 `NOVEL_LLM_API_KEY` 时程序使用确定性 mock：对话回复固定为「（模拟回复）」，`demo` 也能一条命令跑通完整闭环。配了 key 后同样的命令自动换成真实模型，不需要改代码。

### 数据存在哪？怎么换目录？

默认在 `./data`：`global.db` 是作品注册表，每部作品的数据在 `works/<作品ID>/data.db`。想换目录就设置 `NOVEL_DATA_DIR` 再跑命令，首次运行会自动建库（`init` 幂等，可随时重跑）。

### 怎么换 LLM 供应商？

改 `NOVEL_LLM_API_KEY`、`NOVEL_LLM_BASE_URL`、`NOVEL_LLM_MODEL` 三个环境变量，指向任意 OpenAI 兼容的 `/chat/completions` 接口即可，示例见上文「换 LLM 供应商」。

### 质量门怎么调？quality_failed 是什么意思？

阈值默认 8，越小越严格，通过条件与得分公式见上文「质量门」。`quality_failed` 表示最近一次生成或修订没过门：此时不能 `decision accept`，可以 `decision reject` 退掉，或修改风格、调整内容后 `draft revise` 重跑。

### demo 和真实写作有什么区别？

`demo` 是单命令、确定性的端到端演示：自动创建《演示之书》，走「对话 → 生成草稿 → 质量门 → 拍板」，mock 下回复固定，且不设置风格锚点。真实写作是 README 快速开始里的逐条命令，由你自己按节奏推进、给意见、拍板。

### 多部作品会串吗？

不会。每部作品一个独立 SQLite 文件，数据按 `<作品ID>` 隔离，有专门的多作品隔离测试保障。

### 私有记忆的权限规则是什么？

作者只读；伙伴只能以自己的身份写自己的笔记；`--as` 只做权限校验、不落库。完整规则与示例见上文「私有记忆的权限规则」。

### 怎么查看编辑部当前状态？

- `agents show <作品ID>`：完整档案与当前情绪；
- `works show <作品ID>`：班子一览；
- `memory view <作品ID> --as 作者`：老板视图（档案、班子状态、草稿、最近意见与决策）；
- `log <作品ID>`：全流程回顾（对话 / 状态 / 草稿 / 意见 / 决策）；
- `talk list <作品ID>`：对话记录。

### 我配了 .env 为什么不生效？

程序不会自动读取 `.env` 文件。把 `.env` 里的变量用 `export`（bash）或 `$env:`（PowerShell）读入当前会话，或按上文「.env 的用法」由 shell 加载。

### 怎么备份？仓库根目录那个 zip 是什么？

备份 = 复制 `NOVEL_DATA_DIR` 整个目录，恢复时放回原位。仓库根目录的 `novel-editorial-backup-*.zip` 只是仓库备份用途，不是运行时数据的备份机制。

### 命令报错时那个数字是什么意思？

是退出码：`0` 成功、`1` 业务错误、`2` 用法错误、`3` 未预期错误，见上文「退出码」。

### 支持哪些 Python 版本？Windows 能用吗？

Python 3.11 或 3.12（项目约束 `>=3.11,<3.13`），uv 会自动按 `.python-version` 取解释器。Windows、macOS、Linux 都能用，本文档给出了 PowerShell 与 bash 两种写法。
