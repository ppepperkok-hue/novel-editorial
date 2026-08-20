# Novel Editorial

> 分层 AI 文学编辑部：总编、责编、写手、审稿各司其职，作者在关键处拍板，产出「没有 AI 味」的正文。

当前版本 `0.1.0`，纯命令行界面（CLI）。图形面板（三扇窗）是后置项，尚未实现。

仓库：[ppepperkok-hue/novel-editorial](https://github.com/ppepperkok-hue/novel-editorial)

## 这是什么

Novel Editorial 把一个文学编辑部的运作方式做成了本地 CLI：你以作者（老板）身份下达方向，四个 AI 伙伴按自己的岗位与立场协作，讨论、写作、返工、拍板都留有记录，随时可以穿透查看。

- **分层编辑部**：总编、责编、写手、审稿各有自己的判断与记录；协作自然发生——责编会主动追问、写手会反驳、审稿会拦矛盾，作者只在关键节点拍板。
- **伙伴有「自己」**：每个伙伴有完整档案（性格、立场、价值观、审美、情绪基线、工作习惯、弱点、人际预设、私心），情绪随互动变化并留痕，私有记忆互不相通，违背立场会直接拒绝任务。
- **去 AI 味质量门**：按 AI 味词命中、修饰词密度、句式重复、风格一致性打分（默认阈值 8），超限的草稿标记 `quality_failed` 并拦截拍板；`quality explain` 能定位到句并给改写建议。
- **信息分层与按需检索**：写手动笔只拿「写作记忆包」（作品档案、风格、私有记忆、悬置线索），不灌全量历史；`memory search` 跨档案、对话、意见、版本、笔记检索，结果带来源。
- **叙事追踪**：伏笔、目标、钩子三类线索随章节埋设与回收，写手与审稿的提示会带上未回收线索。

## 环境要求与安装

环境要求：

- Python 3.11 或 3.12（项目约束 `>=3.11,<3.13`）
- uv（自带 Python 版本管理与依赖安装）
- 不需要数据库服务：数据存在本地 SQLite 文件里

安装步骤：

```bash
# 1. 安装 uv（Windows 用 PowerShell，macOS / Linux 用 curl）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# 或：curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 进入项目目录
cd novel-editorial

# 3. 安装依赖（自动按 .python-version 取 Python 3.11）
uv sync

# 4. 确认可运行
uv run novel-editorial --version   # 输出 0.1.0
```

配置 LLM（可选）：不配 key 时程序自动使用**确定性 mock**，对话回复固定为「（模拟回复）」，所有命令和 demo 依然可以端到端跑通。想接真实模型时，设置三个环境变量即可：

```bash
export NOVEL_LLM_API_KEY="你的 key"
export NOVEL_LLM_BASE_URL="https://api.deepseek.com"   # 默认值，可换成任何 OpenAI 兼容端点
export NOVEL_LLM_MODEL="deepseek-chat"                 # 默认值
```

Windows PowerShell 写法见 [使用文档](docs/usage.md)。注意：程序只读环境变量，不会自动加载 `.env` 文件。

## 快速开始（30 分钟跑通）

目标：按下面顺序在干净环境跑起一个示例编辑部，产出并拍板第一段内容。所有命令都以 `uv run novel-editorial ...` 开头；下文用 `<作品ID>`、`<草稿ID>` 表示上一步输出里的 id。

**第 1 步：初始化**

```bash
uv run novel-editorial init
initialized: <数据目录>
```

初始化数据目录和 `config.toml`；可重复执行（幂等），配置已存在时会提示 `config exists: ... (kept)`。

**第 2 步：创建作品（自动组建默认班子）**

```bash
uv run novel-editorial works create 雨夜侦探 --genre 悬疑 --description 侦探雨夜回乡查旧案
created workspace <作品ID>: 雨夜侦探
```

记下 `<作品ID>`。想看班子与档案：`uv run novel-editorial works show <作品ID>` / `uv run novel-editorial agents show <作品ID>`。

**第 3 步：定风格锚点**

```bash
uv run novel-editorial style set <作品ID> --description 平实克制短句 --forbidden 璀璨,宛如
style anchor updated: <作品ID>
```

**第 4 步：和编辑部说话**

```bash
uv run novel-editorial talk send <作品ID> 我们写一个雨夜故事，侦探回到故乡。
作者: 我们写一个雨夜故事，侦探回到故乡。
总编: （模拟回复）
责编: 我想先确认一下：这部作品的主角动机和核心冲突，咱们还没对齐吧？这个定不下来，后面每一章都会飘。
```

不带 `@` 默认由总编回答；写 `@写手`、`@责编`、`@审稿`、`@总编`（`主编` 等同 `总编`）指定对象，例如 `talk send <作品ID> @写手，写一段雨夜开场`。首条消息后责编会主动发起追问，这是预期行为。

**第 5 步：查看写作记忆包（写手动笔前拿到的信息）**

```bash
uv run novel-editorial memory pack <作品ID>
作品：《雨夜侦探》（悬疑）
简介：侦探雨夜回乡查旧案
风格说明：平实克制短句
禁忌词：璀璨,宛如
章纲：暂无（占位）
```

**第 6 步：生成草稿**

```bash
uv run novel-editorial draft generate <作品ID> --title "第一章 雨夜"
draft <草稿ID> 第一章 雨夜 now at v1
```

mock 模式下正文是「（模拟回复）」；接真实模型后就是写手按记忆包写的正文。

**第 7 步：过质量门**

```bash
uv run novel-editorial quality check <草稿ID>
passed: True
score: 0.5 (threshold 8)
ai word hits: []
...

uv run novel-editorial quality explain <草稿ID>
未发现明显 AI 味
```

`explain` 在有问题时会逐句定位并给改写建议。分数超过阈值（默认 8）的草稿状态会变成 `quality_failed`，无法被拍板通过。

**第 8 步：责编给意见**

```bash
uv run novel-editorial review add <草稿ID> --from 责编 --content 退稿：开场钩子不成立
review added by 责编: 退稿：开场钩子不成立
```

**第 9 步：写手修订**

```bash
uv run novel-editorial draft revise <草稿ID> --reason 写手反驳：重写铺垫
draft <草稿ID> 第一章 雨夜 now at v2
```

修订会带上上一版正文和已有意见，并自动记录写手的反驳留痕。注意：修订必须在拍板之前（`accepted` 后不能再改）。

**第 10 步：作者拍板**

```bash
uv run novel-editorial decision accept <草稿ID>
draft <草稿ID> accepted
```

也可 `decision reject <草稿ID>`（退稿）或 `decision note <草稿ID> --content ...`（只留言不改状态）。

**第 11 步：穿透回看全流程**

```bash
uv run novel-editorial log <作品ID>
```

输出按「对话 / 状态 / 草稿 / 意见 / 决策」分节，情绪变化也在这里留痕。

**最后：一条命令跑完闭环**

```bash
uv run novel-editorial demo
workspace: <作品ID>
draft: <草稿ID>
quality passed: True (score 0.0)
draft accepted. Run `novel-editorial log <workspace_id>` to review the flow.
```

`demo` 用《演示之书》自动完成「建作品 → 对话 → 生成草稿 → 质量门 → 拍板」，配置了真实 key 就用真实模型，否则用 mock。

**另一条路：`example` 预置编辑部（30 分钟剧本）**

不想从空作品一步步搭，也可以直接要一个预置好的编辑部：

```bash
uv run novel-editorial example
created example workspace <作品ID>: 示例·雨夜车站
Explore: works overview / events list <作品ID> / decision pending <作品ID>
```

不配 key 就能跑（mock 语义，不发网络请求）。它和 `demo` 的区别在于：`demo` 是从零跑一遍动态闭环，跑完即止；`example` 预置了「活的」编辑部《示例·雨夜车站》——班子、风格锚点、设定库、大纲、结构、对话、待拍板草稿、伏笔、记忆、行为与事件流一应俱全，可以直接接着往下操作。

30 分钟体验剧本：

1. `works overview` 看全局；`events list <作品ID>` / `inspect <作品ID> 沈夜` / `decision pending <作品ID>` 穿透看状态；
2. `talk send <作品ID> 我们继续讨论：第一章的雨夜氛围再压一压` 接着聊；
3. `draft revise <草稿ID> --reason 按讨论返工` 返工（示例草稿在拍板前可改）；
4. `decision accept <草稿ID>` 拍板。

`example` 每次执行都新建一个示例作品（ID 不同），不覆盖旧数据，也不动既有作品与配置；清理 = 删除对应数据目录 `NOVEL_DATA_DIR/works/<作品ID>`，程序不提供破坏性删除命令。

## 命令速查

- `works`：`create`（创建作品）/ `list` / `show`
- `agents`：`show`（完整档案与当前状态）/ `edit`（改档案字段）
- `talk`：`send`（说话，`@别名` 指定对象）/ `list`（对话记录）
- `style`：`set`（风格与禁忌词）/ `show`
- `memory`：`pack`（写作记忆包）/ `note`（写私有记忆）/ `notes`（列私有记忆）/ `view`（分层视图）/ `search`（带来源检索）/ `delete`
- `draft`：`generate` / `revise` / `list` / `show` / `diff`
- `review`：`add`（给意见）/ `list`
- `decision`：`accept` / `reject` / `note` / `list` / `pending`（待拍板清单）
- `quality`：`check`（打分与通过与否）/ `explain`（定位句与改写建议）
- `plot`：`plant`（埋线索）/ `list` / `recover`（回收线索）
- `events`：`list`（事件回放）/ `watch`（增量观察新事件）
- `inspect`：`<作品ID> <关键词>`（老板跨层检索，结果带来源）
- 其他：`init` / `health` / `version` / `demo` / `example` / `log`

完整选项看 `uv run novel-editorial <命令> --help`。

## 数据与隐私

- 数据目录由 `NOVEL_DATA_DIR` 指定（默认 `./data`）：`global.db` 是作品注册表，每部作品有独立库 `works/<作品ID>/data.db`，多作品互不串扰。
- API key 只经环境变量传入，不写进数据库，也不会进 git（`.env`、`config.toml`、`data/` 已被 `.gitignore` 忽略）。
- 未配置 key 时程序不发任何网络请求；配置后仅在调用所选 LLM 供应商时发送请求内容，无其他上报。
- 备份 = 复制整个数据目录。仓库根目录的 `novel-editorial-backup-*.zip` 只是仓库备份用途，不是运行时数据备份。

## 更多

- 配置、环境变量清单与常见问题：[docs/usage.md](docs/usage.md)
- 核心目标与里程碑：[docs/project-plan/03-core-goals.md](docs/project-plan/03-core-goals.md)、[docs/project-plan/05-executable-units.md](docs/project-plan/05-executable-units.md)
- 仓库与反馈：[ppepperkok-hue/novel-editorial](https://github.com/ppepperkok-hue/novel-editorial)（提 Issue / 提 PR 都在这里）

开发与验证命令：

```bash
uv run pytest -q -n auto          # 全量并行（与 CI 同一套）
uv run pytest -q -m smoke         # 快速核心闭环子集（约 30 个代表用例）
uv run pytest -q --lf             # 只重跑上次失败用例
uv run ruff check .
uv run pyright
python scripts/verify_constitution.py
```
