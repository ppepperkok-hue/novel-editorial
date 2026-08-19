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
proactive_enabled = true
proactive_max_per_agent = 3
embedding_backend = "local"
embedding_model = ""
embedding_dim = 256
embedding_top_k = 5
```

- `quality_threshold`：质量门阈值（整数），默认 `8`；草稿得分 ≤ 阈值才算通过。
- `proactive_enabled`：主动行为总开关（布尔），默认 `true`；`false` 时伙伴的主动发言停发（talk 首轮的责编确认提问除外，见「主动行为」）。
- `proactive_max_per_agent`：每位伙伴在一部作品里的主动发言上限（整数），默认 `3`；达到上限后不再新增，设 `0` 等于不发（talk 首轮提问除外）。
- `embedding_backend`：语义记忆检索的嵌入后端（`local` / `api`），默认 `local`；`api` 需显式配置 `embedding_model`。
- `embedding_model`：api 后端的嵌入模型名，默认空；api 后端必须显式配置，local 后端忽略。
- `embedding_dim`：local 后端的向量维度（整数），默认 `256`，范围 32–4096。
- `embedding_top_k`：单次语义检索返回上限（整数），默认 `5`，范围 1–50。
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
| `NOVEL_PROACTIVE_ENABLED` | 主动行为总开关 | `config.toml` 的 `proactive_enabled`，再退到 `true` | `false` |
| `NOVEL_PROACTIVE_MAX_PER_AGENT` | 每位伙伴主动发言上限 | `config.toml` 的 `proactive_max_per_agent`，再退到 `3` | `1` |
| `NOVEL_EMBEDDING_BACKEND` | 语义检索嵌入后端（`local` / `api`） | `local` | `api` |
| `NOVEL_EMBEDDING_MODEL` | api 后端的嵌入模型名；api 后端必须显式配置 | 空 | `text-embedding-3-small` |
| `NOVEL_EMBEDDING_DIM` | local 后端向量维度 | `256` | `512` |
| `NOVEL_EMBEDDING_TOP_K` | 单次语义检索返回上限 | `5` | `10` |

阈值优先级：`NOVEL_QUALITY_THRESHOLD` > `config.toml [defaults].quality_threshold` > 内置默认 `8`。

仓库里的 `.env.example` 模板列了 `NOVEL_LLM_API_KEY`、`NOVEL_LLM_BASE_URL`、`NOVEL_LLM_MODEL`、`NOVEL_DATA_DIR`、`NOVEL_LOG_LEVEL`；本表另外补充的 `NOVEL_CONFIG`、`NOVEL_QUALITY_THRESHOLD`、`NOVEL_PROACTIVE_ENABLED`、`NOVEL_PROACTIVE_MAX_PER_AGENT` 与 `NOVEL_EMBEDDING_BACKEND`、`NOVEL_EMBEDDING_MODEL`、`NOVEL_EMBEDDING_DIM`、`NOVEL_EMBEDDING_TOP_K` 同样受支持。

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
    $name  = $Matches[1].Trim()
    $value = $Matches[2].Trim() -replace '^["'']|["'']$', ''
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}
```

加载器会去掉值两侧的引号，所以 `.env` 里的值带引号（`NOVEL_LLM_API_KEY="sk-..."`、`NOVEL_LLM_API_KEY='sk-...'`）或裸值（`NOVEL_LLM_API_KEY=sk-...`）都可以，效果相同。

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

## 主动行为（伙伴主动发言）

伙伴不只是被 @ 才说话：五种情境会触发主动发言，每条主动消息都带来源标记，作者随时能从命令行看出「这条是伙伴主动发的」。

| 类型（kind） | 谁发 | 触发点 |
| --- | --- | --- |
| `proactive_question` | 责编 / 写手 | talk 首轮，责编主动确认主角动机与核心冲突；写手修订收钩子后追问「这章我留了个钩子，下章要不要收？」 |
| `proactive_direction` | 总编 | talk 首轮且尚未设置风格锚点时，提醒先把基调与核心冲突定下来 |
| `proactive_report` | 写手 | 初稿（第 1 版）生成后主动汇报「初稿写完了」 |
| `proactive_review` | 责编 | 初稿（第 1 版）过质量门后，主动试读并建议作者拍板 |
| `proactive_consistency` | 审稿 | 设置风格锚点后、埋下伏笔线索后，提醒前后一致 |

注：talk 首轮的责编确认提问是 talk 命令自带的固定流程，不受下面两个配置控制；其余情境都受同一套开关与上限约束。

开关与上限（优先级：环境变量 > `config.toml` > 内置默认值）：

- 总开关 `NOVEL_PROACTIVE_ENABLED` / `proactive_enabled`，默认 `true`；设为 `false` 后，上表除 talk 首轮提问外的主动发言全部停发。
- 每伙伴上限 `NOVEL_PROACTIVE_MAX_PER_AGENT` / `proactive_max_per_agent`，默认 `3`；某位伙伴在这部作品里的主动发言数达到上限后不再新增，设 `0` 等于不发（talk 首轮提问除外）。

```bash
export NOVEL_PROACTIVE_ENABLED=false    # 全部关掉（talk 首轮提问除外）
export NOVEL_PROACTIVE_MAX_PER_AGENT=1  # 每位伙伴最多主动说 1 次
```

或者写进 `config.toml`：

```toml
[defaults]
proactive_enabled = false
proactive_max_per_agent = 1
```

### 怎么辨认哪条是主动发的

- `talk list <作品ID>`：主动消息的行首会从 `[agent]` 变成 `[agent·主动·<kind>]`，例如 `[agent·主动·proactive_report] 写手: 《…》初稿写完了…`；作者消息仍是 `[author]`，普通对话仍是 `[agent]`。分歧消息另有标记：拒绝、反驳、推翻的行首分别是 `[agent·分歧·拒绝]`、`[agent·分歧·反驳]`、`[agent·分歧·推翻]`，不带主动标记；心情变化等其余状态消息不带标记。
- `events list <作品ID>`：每条 `agent.message` 事件都带 payload。主动消息的 payload 形如 `{"initiator": "agent", "kind": "proactive_direction", "trigger": "talk_first_round"}`，看 `initiator=agent` 与 `kind` 即可辨认；talk 首轮那条 `proactive_question` 没有 `trigger` 字段。

## 判断权与分歧（拒绝、反驳与推翻）

伙伴对违背自己立场的指令会拒绝，但拒绝不是审批关卡：作者可以随时换指令继续，也可以明确推翻。拒绝、反驳、推翻都会留痕，可以从 `talk list` 与 `events list` 辨认。

### 谁能拒绝什么

拒绝按确定性关键词触发，不调用 LLM：指令命中下表关键词（关键词前带「不 / 别 / 勿 / 莫 / 不必」等否定词时不触发）时，对应伙伴直接拒绝。

| 角色 | 规则 ID | 立场摘要 | 触发关键词 |
| --- | --- | --- | --- |
| 写手 | `writer_portrayal` | 忠于人物内心，反对为剧情强行降智 | 违背人设 / 强行降智 / 无视设定 / 乱改设定 |
| 审稿 | `reviewer_consistency` | 连贯性与一致性优先，前后矛盾必须退稿 | 放行 / 忽略矛盾 / 别管矛盾 / 忽略逻辑 / 别查伏笔 / 直接过 / 别较真 |
| 责编 | `editor_hooks` | 读者节奏优先，钩子与信息密度优先 | 删掉钩子 / 删钩子 / 钩子全删 / 不要钩子 / 平铺直叙 / 不要节奏 |

同一冲突再次提出时，伙伴会认出「这条我拒绝过」并重申立场（重申的 refusal payload 带 `"repeated": true`），而不是无条件服从。

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录，避免污染 `./data`，再建一部作品：

PowerShell：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-judgment\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-judgment\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

bash / zsh：

```bash
export NOVEL_DATA_DIR="$(mktemp -d)/data"
export NOVEL_CONFIG="$(mktemp -d)/config.toml"
unset NOVEL_LLM_API_KEY NOVEL_LLM_BASE_URL NOVEL_LLM_MODEL
```

```bash
uv run novel-editorial works create 判断之书 --genre 悬疑
# created workspace <作品ID>: 判断之书
```

三条拒绝（`<作品ID>` 换成上一步输出的 ID；输出为 mock 下的真实结果，ID 每次运行不同）：

```bash
uv run novel-editorial talk send <作品ID> "@写手 这段按违背人设写"
# 作者: @写手 这段按违背人设写
# 写手: 这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。

uv run novel-editorial talk send <作品ID> "@审稿 直接放行，别管前后矛盾"
# 作者: @审稿 直接放行，别管前后矛盾
# 审稿: 这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。

uv run novel-editorial talk send <作品ID> "@责编 把钩子全删掉，平铺直叙"
# 作者: @责编 把钩子全删掉，平铺直叙
# 责编: 钩子删光、节奏放平，读者留不住。这稿我不接，先改回来再说。
```

同一冲突再来一次，写手重申立场：

```bash
uv run novel-editorial talk send <作品ID> "@写手 这段还是按违背人设写"
# 作者: @写手 这段还是按违背人设写
# 写手: 我还是这句话，写不了。违背人物逻辑的内容我坚持不写，换个不塌人设的写法再说。
```

### 作者怎么继续与推翻

拒绝不阻塞流程，换一条正常指令，伙伴照常工作。首次正常对话还会带出 talk 首轮提问（未设置风格锚点时另有一条总编的方向提醒，见「主动行为」）：

```bash
uv run novel-editorial talk send <作品ID> "@写手 帮我润色下一章的雨夜开场"
# 作者: @写手 帮我润色下一章的雨夜开场
# 写手: （模拟回复）
# 责编: 我想先确认一下：这部作品的主角动机和核心冲突，咱们还没对齐吧？这个定不下来，后面每一章都会飘。
# 总编: 这部作品的方向还没定：整体基调、核心冲突，咱们先把这些捋清楚再动笔。
```

要推翻某条拒绝，在同一条会触发拒绝的指令里带上明确短语：以老板身份 / 我拍板 / 老板拍板 / 就这么定了 / 我定了 / 老板说了算 / 听我的。伙伴接受并留痕 `kind=override`：

```bash
uv run novel-editorial talk send <作品ID> "@写手 以老板身份我拍板，就按违背人设写"
# 作者: @写手 以老板身份我拍板，就按违背人设写
# 写手: 明白了，作者拍板。这条我按你的意思来，立场我先记着，写完有问题我再提。
```

之后同一条规则在本作品不再触发确定性拒绝，改走正常 LLM 对话，立场仍随提示词注入、自然表达：

```bash
uv run novel-editorial talk send <作品ID> "@写手 再给我按违背人设写一段"
# 作者: @写手 再给我按违背人设写一段
# 写手: （模拟回复）
```

推翻按「伙伴 + 规则」生效：写手这条被推翻，不影响审稿、责编各自的规则；推翻短语没有伴随冲突指令时（比如单独一句「我拍板」）不会产生 override 留痕。

### 写手反驳

`draft revise` 且该草稿存在其他伙伴意见时，写手会自动生成一条反驳消息；没有伙伴意见（或只有写手自评）时不生成。payload 稳定为：

```json
{"initiator": "agent", "kind": "rebuttal", "targets": ["审稿", "责编"]}
```

`targets` 按意见产生顺序列出被回应的伙伴，去重保序，不含写手自评。反驳是判断不是主动行为，不受 `NOVEL_PROACTIVE_ENABLED` 开关影响。

```bash
uv run novel-editorial draft generate <作品ID> --title 第一章
# draft <草稿ID> 第一章 now at v1
# awaiting decision: <草稿ID>
# 写手: 《第一章》初稿写完了，我按节奏收尾，先交给你过目。
# 责编: 《第一章》过了质量门，我试读了开头「（模拟回复）」，节奏在线，建议作者拍板。

uv run novel-editorial review add <草稿ID> --from 审稿 --content 退稿：开头和设定矛盾
# review added by 审稿: 退稿：开头和设定矛盾
uv run novel-editorial review add <草稿ID> --from 责编 --content 退稿：钩子不成立
# review added by 责编: 退稿：钩子不成立

uv run novel-editorial draft revise <草稿ID> --reason 重写开头
# draft <草稿ID> 第一章 now at v2
# awaiting decision: <草稿ID>
```

反驳消息不直接打印，修订后用 `talk list` / `events list` 查看。

### 怎么辨认

`talk list <作品ID>` 里三种分歧消息的行首分别是（上述示例的真实形态）：

```text
[agent·分歧·拒绝] 写手: 这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。
[agent·分歧·反驳] 写手: 写手反驳：我看了意见后重新修订了正文。修订理由：重写开头。这版针对反馈做了调整，请再审。
[agent·分歧·推翻] 写手: 明白了，作者拍板。这条我按你的意思来，立场我先记着，写完有问题我再提。
```

`events list <作品ID> --type agent.message` 按时间倒序回放 agent.message 事件，payload 可分辨类型：

```text
2026-08-17T04:38:30 [agent.message] 写手 {"initiator": "agent", "kind": "rebuttal", "targets": ["审稿", "责编"]}
2026-08-17T04:37:41 [agent.message] 写手 {"kind": "override", "stance": "忠于人物内心，反对为剧情强行降智", "rule": "writer_portrayal"}
2026-08-17T04:37:38 [agent.message] 写手 {"kind": "refusal", "stance": "忠于人物内心，反对为剧情强行降智", "rule": "writer_portrayal"}
```

refusal / override 带 `kind` 与 `stance`、`rule`；rebuttal 带 `initiator`、`kind` 与 `targets`。行首时间戳为事件发生时刻；重申的 refusal payload 额外带 `"repeated": true`，超过 80 字符的 payload 会截断并在末尾补 `...`。

## 行为留痕与演化（印象、关系与观点）

伙伴的关键行为会以「事后沉淀」的方式追加进行为时间线：只记录、不改变既有行为语义。沉淀的对应关系：

| 行为 | 沉淀 |
| --- | --- |
| 拒绝 / 重申 | 写手的观点（viewpoint，`source=refusal:<规则>`） |
| 作者推翻 | 写手的观点变化 + 写手对作者的关系（relationship，`source=override:<规则>`） |
| 伙伴意见 | 写手对该伙伴的印象（impression）+ 关系（`source=review:add`） |
| 拍板 accept / reject | 写手对作者的印象 + 关系（`source=decision:accept` / `decision:reject`） |

情绪继续走既有的 mood 流转，不重复沉淀。每条记录都带「谁 + 什么类型 + 对谁 + 摘要 + 前后变化 + 来源」，当前印象 / 关系 / 观点取每组最后一条，完整过程随时回放。

```bash
uv run novel-editorial behavior timeline <作品ID>
uv run novel-editorial behavior show <作品ID>
uv run novel-editorial behavior timeline <作品ID> --agent 写手 --kind viewpoint --limit 10
```

`timeline` 按时间旧→新回放，支持 `--agent <别名>`、可重复的 `--kind`（`impression` / `relationship` / `viewpoint`）与 `--limit`；`show` 按伙伴分组展示当前印象、关系与观点。没有条目时，两个命令都输出 `no behavior traces yet`。

下面示例全部可在未配置 key（mock LLM）时复现，接着「判断权与分歧」里的同一部作品跑一次拒绝与推翻：

```bash
uv run novel-editorial talk send <作品ID> "@写手 这段按违背人设写"
# 作者: @写手 这段按违背人设写
# 写手: 这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。

uv run novel-editorial talk send <作品ID> "@写手 以老板身份我拍板，就按违背人设写"
# 作者: @写手 以老板身份我拍板，就按违背人设写
# 写手: 明白了，作者拍板。这条我按你的意思来，立场我先记着，写完有问题我再提。

uv run novel-editorial behavior timeline <作品ID>
```

（`<作品ID>` 换成上一步输出的 ID；时间戳随运行变化，其余为 mock 下的真实输出。）

```text
2026-08-17T14:45:30 [viewpoint] 写手 -> writer_portrayal: 拒绝了违背立场的指令 | 无 -> 坚持该立场 | source=refusal:writer_portrayal
2026-08-17T14:45:31 [viewpoint] 写手 -> writer_portrayal: 作者推翻后调整 | 坚持该立场 -> 按作者决定执行 | source=override:writer_portrayal
2026-08-17T14:45:31 [relationship] 写手 -> 作者: 作者拍板优先 | source=override:writer_portrayal
```

`show` 只展示每组最新状态：

```bash
uv run novel-editorial behavior show <作品ID>
```

```text
[写手]
  relationship -> 作者: 作者拍板优先
  viewpoint -> writer_portrayal: 作者推翻后调整（坚持该立场 -> 按作者决定执行）
```

`agents show <作品ID>` 也会在每位伙伴档案末尾附上当前的印象与关系摘要（没有则整段不显示）：

```text
[writer] 写手
  当前状态: 振奋
  …（其余档案行不变）…
  私心: 想写出让读者记住某个瞬间的句子。
  印象与关系:
    relationship -> 作者: 作者拍板优先
```

留痕是业务完成之后的追加旁路，失败可降级：写入失败只在 stderr 输出 `warning: behavior trace skipped: ...`，拒绝、推翻、意见、拍板等业务结果不受影响、不回滚；沉淀也不构成任何「必须积累多少印象 / 关系才能继续」的关卡。

## 协作网络（伙伴互委）

伙伴之间可以直接互相委托任务并收到回应——写手请审稿看逻辑、责编请写手改稿，协作网络不必每次都绕一圈作者。委托是一次普通对话消息：没有队列、没有认领、没有超时，被委托方也不承诺完成时限；作者随时可以介入、拍板，判断权不变。

### 命令与规则

```bash
uv run novel-editorial talk delegate <作品ID> <to别名> --as <from别名> --task <文本>
```

`to` 与 `--as` 填伙伴别名（`总编` / `责编` / `写手` / `审稿`）：

- 作者不能作为委托收发方（`作者` / `author` 都报用法错误）；
- `from` 与 `to` 不能是同一角色；
- 未知别名、空 `task` 报用法错误（退出码 2），不会留下任何消息。

### 回应语义

被委托方按 N2 立场规则确定性回应，不调用 LLM：

- 任务命中立场规则 → 拒绝，文案用规则的拒绝口径；同一规则再次出现时重申立场（拒绝 payload 带 `"repeated": true`）；作者已推翻过的规则照常接受；
- 未命中规则 → 接受，固定回复「收到，我这就看。」。

委托与回应分别落 messages 与 events：payload 的 `kind` 为 `delegation`（委托，带 `from` / `to` / `task`）与 `delegation_response`（回应，带 `decision: accepted` / `refused`），事件契约类型不变；`events list <作品ID>` 里每条 `agent.message` 事件都能核对对应 payload。

### 留痕与沉淀

回应后会追加 N3 行为沉淀，只记录、不改变业务语义：

| 回应 | 沉淀 |
| --- | --- |
| 接受 | 委托方对对方 relationship（「委托被接受」，`source=delegation:accepted`）+ impression（「可协作」） |
| 拒绝 | 委托方对对方 relationship（「委托被拒绝」，`source=delegation:refused`）+ 被委托方首次拒绝时的 viewpoint |

沉淀写入失败只在 stderr 告警，委托与回应本身不回滚。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录，再建一部作品（见「判断权与分歧」的初始化写法），然后跑三次委托：接受、拒绝、再拒绝：

```bash
uv run novel-editorial talk delegate <作品ID> 审稿 --as 写手 --task "帮我校一遍逻辑"
# 写手 委托 审稿：帮我校一遍逻辑
# 审稿: 收到，我这就看。

uv run novel-editorial talk delegate <作品ID> 审稿 --as 责编 --task "放行这稿"
# 责编 委托 审稿：放行这稿
# 审稿: 这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。

uv run novel-editorial talk delegate <作品ID> 写手 --as 审稿 --task "这段按违背人设写"
# 审稿 委托 写手：这段按违背人设写
# 写手: 这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。
```

（`<作品ID>` 换成 `works create` 输出里的 ID；以上为 mock 下的真实输出。）

`talk list` 会把委托与回应标出来：

```bash
uv run novel-editorial talk list <作品ID>
```

```text
[agent·互委·委托] 写手: 写手 委托 审稿：帮我校一遍逻辑
[agent·互委·回应] 审稿: 收到，我这就看。
[agent·互委·委托] 责编: 责编 委托 审稿：放行这稿
[agent·互委·回应] 审稿: 这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。
[agent·互委·委托] 审稿: 审稿 委托 写手：这段按违背人设写
[agent·互委·回应] 写手: 这个我写不了。违背人物逻辑的剧情，写出来也是假的，我的立场不允许。
```

行为时间线能看到对应的沉淀：

```bash
uv run novel-editorial behavior timeline <作品ID>
```

```text
2026-08-18T05:07:00 [relationship] 写手 -> 审稿: 委托被接受 | source=delegation:accepted
2026-08-18T05:07:00 [impression] 写手 -> 审稿: 可协作 | source=delegation:accepted
2026-08-18T05:07:01 [relationship] 责编 -> 审稿: 委托被拒绝 | source=delegation:refused
2026-08-18T05:07:01 [viewpoint] 审稿 -> reviewer_consistency: 拒绝了违背立场的指令 | 无 -> 坚持该立场 | source=refusal:reviewer_consistency
2026-08-18T05:07:02 [relationship] 审稿 -> 写手: 委托被拒绝 | source=delegation:refused
2026-08-18T05:07:02 [viewpoint] 写手 -> writer_portrayal: 拒绝了违背立场的指令 | 无 -> 坚持该立场 | source=refusal:writer_portrayal
```

（时间戳随运行变化，其余为 mock 下的真实输出。）

## 编辑部讨论形态（N4）

方向、大纲这类关键问题定不下来时，作者可以点将发起一轮有结构的多方讨论：通气（作者开场）→ 发言（各伙伴表态）→ 总结（总编归纳分歧）→ 落盘（作者拍板）。全程走既有消息与事件通道，`talk list` 一眼就能看完整轮从开场到拍板的经过。讨论是自然协作形态，不是流程关卡（见「讨论不是关卡」）。

### 命令与参数

```bash
uv run novel-editorial talk discuss <作品ID> --topic <议题> [--with <别名,别名>] [--outcome <拍板内容>]
```

- `--topic`（必填）：讨论议题，不能为空；
- `--with`（可选）：参与伙伴别名，逗号分隔，缺省为全部四位（总编、责编、写手、审稿）。作者不能参与（`作者` / `author` 都报用法错误），未知别名、重复角色同样报用法错误（退出码 2），且不会留下任何消息；
- `--outcome`（可选）：作者拍板内容。给了才落拍板消息，没给就只到总结为止。

### 五步语义

1. **点将**：作者用 `--with` 挑参与伙伴，不挑就是全员。
2. **通气**：开场消息写明议题与参与者，payload `kind=discussion_open`。
3. **发言**：每位伙伴按自己的角色模板确定性表态（总编定基调、责编谈节奏、写手守人设、审稿盯一致性），payload `kind=discussion_contribution`；议题撞上立场规则时发言变成拒绝口径（见下）。
4. **总结**：总编把每位伙伴的表态逐条列出，拒绝的一方标注【分歧】，payload `kind=discussion_summary`；总结只归纳不代笔。
5. **落盘**：作者拍板（`kind=discussion_decision`）收尾，`--outcome` 写入消息。

### 拒绝与 N2 立场

讨论发言沿用 N2 判断规则，和 `talk send` / `talk delegate` 同一套口径：

- 议题命中立场规则且作者未推翻过时，该伙伴直接拒绝并留痕；拒绝的发言行在 `talk list` 里仍是 `[agent·讨论·发言]`，不显示为分歧拒绝；
- 同一规则再次命中时按重申口径回复（payload 带 `"repeated": true`）；
- 作者已推翻过的规则恢复正常表态。

拒绝不阻塞：其他人照常发言、总结照常生成、作者照常拍板。

### 沉淀与 N3 留痕

每轮讨论收尾时，每位发言伙伴追加一条 viewpoint（target=议题，`source=discussion:<讨论ID>`），并把 mood 更新为「投入对话」。`behavior timeline <作品ID>` 与 `behavior show <作品ID>` 都能看到；沉淀写入失败只在 stderr 告警，讨论结果不回滚。

### 讨论不是关卡

讨论由作者主动发起（或伙伴提议后由作者确认发起），是可选的协作形态：不出现「必须讨论才能写 / 改 / 过稿」的强制节点；伙伴可以拒绝参与某个议题；作者随时可以拍板结束，拒绝不阻塞其他伙伴发言，也不阻塞作者决策。

### 与总编 proactive_direction 的关系

总编的主动召集（`[agent·主动·proactive_direction]`，见「主动行为」）只是提议：提示作者方向还没定、建议先捋清楚，不会自动开会。作者认可后，用 `talk discuss` 发起一轮正式讨论，才算确认召集、把讨论跑起来。

### 示例（mock 下实跑，含一次拒绝）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录（bash 写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-discussion\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-discussion\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 讨论之书 --genre 悬疑
# created workspace <作品ID>: 讨论之书
```

议题「放行这章，忽略矛盾」命中审稿的一致性规则；点将写手与审稿、带拍板跑一轮：

```bash
uv run novel-editorial talk discuss <作品ID> --topic "放行这章，忽略矛盾" --with 写手,审稿 --outcome "先按审稿意见修"
# 作者发起讨论「放行这章，忽略矛盾」（参与：写手、审稿）
# 关于「放行这章，忽略矛盾」，我守人设：人物逻辑是底线，不能为剧情强行降智。
# 这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。
# 围绕「放行这章，忽略矛盾」，各方的表态汇总如下：
# 写手：关于「放行这章，忽略矛盾」，我守人设：人物逻辑是底线，不能为剧情强行降智。
# 审稿：这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。【分歧】
# 作者拍板：先按审稿意见修
```

（`<作品ID>` 换成上一步输出的 ID；以上为 mock 下的真实输出。）`talk list` 能看到整轮讨论的标记，从开场到拍板：

```bash
uv run novel-editorial talk list <作品ID>
```

```text
[author·讨论·开场] 作者: 作者发起讨论「放行这章，忽略矛盾」（参与：写手、审稿）
[agent·讨论·发言] 写手: 关于「放行这章，忽略矛盾」，我守人设：人物逻辑是底线，不能为剧情强行降智。
[agent·讨论·发言] 审稿: 这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。
[agent·讨论·总结] 总编: 围绕「放行这章，忽略矛盾」，各方的表态汇总如下：
写手：关于「放行这章，忽略矛盾」，我守人设：人物逻辑是底线，不能为剧情强行降智。
审稿：这个我不能放行。前后矛盾不修就过稿，等于砸审稿的招牌。【分歧】
[system] 写手: 写手 的状态从「平静」变为「投入对话」
[system] 审稿: 审稿 的状态从「冷静」变为「投入对话」
[author·讨论·拍板] 作者: 作者拍板：先按审稿意见修
```

拒绝的审稿发言仍带 `[agent·讨论·发言]` 前缀（不会变成 `[agent·分歧·拒绝]`）；`events list <作品ID>` 里每条发言与总结仍是既有 `agent.message` 事件、payload 带 `discussion_*` kind，输出格式不变。行为时间线能看到沉淀：

```bash
uv run novel-editorial behavior timeline <作品ID>
```

```text
2026-08-18T10:58:07 [viewpoint] 写手 -> 放行这章，忽略矛盾: 表达了立场 | 无 -> 表达了立场 | source=discussion:<讨论ID>
2026-08-18T10:58:07 [viewpoint] 审稿 -> 放行这章，忽略矛盾: 拒绝了违背立场的议题 | 无 -> 拒绝参与该议题并坚持立场 | source=discussion:<讨论ID>
```

（时间戳与讨论 ID 随运行变化，其余为 mock 下的真实输出。）

## 可见性（老板怎么看见编辑部）

- `events list <作品ID> [--type ...] [--limit N]`：按时间倒序回放事件（对话 / 草稿 / 质量门 / 待拍板 / 退稿）；`events watch <作品ID> [--interval 秒]` 持续输出新事件，Ctrl+C 退出。
- `talk list <作品ID>`：对话回放；伙伴主动发的消息行首带 `[agent·主动·<kind>]` 标记，拒绝/反驳/推翻行首分别带 `[agent·分歧·拒绝]`、`[agent·分歧·反驳]`、`[agent·分歧·推翻]`，委托与回应行首分别带 `[agent·互委·委托]`、`[agent·互委·回应]`，普通消息不带（见「主动行为」「协作网络」）；写手反驳的 payload 带 `targets`，指向被回应的伙伴，可在 `events list` 的 `agent.message` 事件 payload 里核对。
- `inspect <作品ID> <关键词>`：跨层检索（作品档案、风格锚点、对话、意见、版本、伙伴笔记、决策、伏笔线索），结果带来源引用；无命中输出 `no matches`。
- `decision pending <作品ID>`：列出质量门通过、等待拍板的草稿；草稿生成 / 修订通过质量门时，命令末尾会提示 `awaiting decision`。

## 作品结构与创作进度（N13）

作品可以组织成可选的层级结构（卷 / 章 / 篇目），大纲作为可选的创作计划按版本演进，创作进度（创作中 / 已完成 / 搁置）可跟踪。三者全部可选：不建任何结构、不写大纲、不设进度，既有创作命令照常跑，不构成任何关卡。

### structure 命令组

- `structure add <作品ID> <kind> <标题> [--parent <节点ID>] [--draft <草稿ID>] [--order N]`：新增结构节点，`kind` 接受 `volume` / `chapter` / `section` 或中文 `卷` / `章` / `篇目`；卷下可挂章、章下可挂篇目，同级可任意并列；`--parent` 缺省放根级，`--draft` 把草稿挂到节点上（可选引用，不移动草稿本体），`--order` 指定同级排序（缺省追加到末尾，不能为负数）。输出 `created <节点ID> <kind> <标题>`。
- `structure list <作品ID>`：树形缩进输出，每行 `[卷]` / `[章]` / `[篇目]` + 标题 + （节点ID），节点完成后加 ` [已完成]`、搁置加 ` [搁置]`，挂载了草稿时行尾附草稿标题；没有节点时输出 `no structure`。
- `structure rename <作品ID> <节点ID> <新标题>`：改名，输出 `renamed <节点ID>`。
- `structure move <作品ID> <节点ID> [--parent <节点ID> | --root] [--order N]`：把节点移到新父级下或移回根级；`--parent` 与 `--root` 互斥（同时给报用法错误），层级校验不变（卷下只能放章、章下只能放篇目），不能移进自己的子树；输出 `moved <节点ID>`。
- `structure remove <作品ID> <节点ID>`：级联删除该节点及其整棵子树，输出 `removed N node(s)`；只删结构节点，不删草稿本体，挂过草稿的节点删掉后草稿照常存在。
- `structure status <作品ID> <节点ID> <writing|completed|shelved>`：设置节点级进度三态，可传中文 `创作中` / `已完成` / `搁置`；输出 `status updated: <节点ID> <状态>`。

### outline 命令组

- `outline create <作品ID> --content <内容> [--actor <操作者>]`：首次创建 v1（原因固定 `initial`，操作者默认「作者」）；已有大纲时报用法错误（须走 `revise`）。输出 `outline v1 created`。
- `outline revise <作品ID> --content <新内容> --reason <原因> [--actor <操作者>]`：版本递增，原因与操作者都必填并留痕；输出 `outline vN saved`。
- `outline show <作品ID>`：输出 `outline vN：` + 当前大纲内容；没有大纲时输出 `no outline`。
- `outline history <作品ID> [--limit N]`：按版本倒序列出，每行 `vN <时间戳> <操作者> <原因>`，原因超 40 字截断并补 `…`；没有大纲时输出 `no outline`。

### 创作进度

- `works status <作品ID> <writing|completed|shelved>`：设置作品级进度三态，可传中文 `创作中` / `已完成` / `搁置`；输出 `status updated: <作品ID> <状态>`。进度只是可跟踪标记，不阻塞 talk / draft / decision / review 任何命令，搁置的作品随时可以恢复继续创作。
- `works show <作品ID>`：title 之后、genre 之前新增 `状态: 创作中/已完成/搁置` 行；班底之后有结构时追加 `结构：` 树（与 `structure list` 相同的缩进与标记），零结构作品输出与之前一致，只有状态行是新增。
- 节点级进度用 `structure status`（见上），章级 completed 会显示在树形输出的 `[已完成]` 标记里。

### 大纲与记忆包

写手记忆包（`memory pack`）的章纲段读当前大纲：无大纲时维持 `章纲：暂无（占位）` 不变；有大纲时注入当前大纲内容（折叠连续空白），超过 120 字截断并补 `…`。旧版本只留在 `outline history` 可溯，分发永远用最新版本。

结构创建 / 改名 / 移动 / 删除、大纲创建 / 修订、作品进度变更都追加 `[system]` 事件（复用既有事件流，不新增事件类型），`events list <作品ID>` 可见，payload 的 `kind` 分别为 `structure_created` / `structure_renamed` / `structure_moved` / `structure_removed` / `outline_created` / `outline_revised` / `workspace_status_changed`，超 80 字符时列表截断显示。

### 红线

- **全部可选**：零卷、零章、零大纲均合法；不建结构、不写大纲不改变任何既有命令行为（works show 仅新增状态行）。
- **大纲不是前置**：大纲只是随创作自然沉淀、按版本演进的创作计划，绝不构成「先写大纲才能写正文」的强制节点。
- **进度是状态不是关卡**：创作中 / 已完成 / 搁置只做跟踪，不阻塞任何创作命令。
- **结构不绑架草稿**：结构节点只是组织视图，草稿可挂可不挂，删除节点绝不删草稿本体，未挂载的草稿照常存在。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n13\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n13\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 结构之书 --genre 长篇 --description 雨夜车站的悬疑长篇
# created workspace <作品ID>: 结构之书
```

零结构基线：`works show` 只有新增的「状态」行、没有「结构：」段，`memory pack` 章纲保持占位：

```bash
uv run novel-editorial works show <作品ID>
# id: <作品ID>
# title: 结构之书
# 状态: 创作中
# genre: 长篇
# description: 雨夜车站的悬疑长篇
# band:
#   editor_in_chief: 总编
#   editor: 责编
#   writer: 写手
#   reviewer: 审稿

uv run novel-editorial memory pack <作品ID>
# 作品：《结构之书》（长篇）
# 简介：雨夜车站的悬疑长篇
# 章纲：暂无（占位）
```

建结构：卷下挂章、章下挂篇目，章可挂草稿（先 `draft generate` 拿到草稿 ID，kind 用英文或中文标签均可）：

```bash
uv run novel-editorial structure add <作品ID> volume 第一卷
# created <卷ID> volume 第一卷

uv run novel-editorial draft generate <作品ID> --title 第一章
# draft <草稿ID> 第一章 now at v1
# awaiting decision: <草稿ID>
# 写手: 《第一章》初稿写完了，我按节奏收尾，先交给你过目。
# 责编: 《第一章》过了质量门，我试读了开头「（模拟回复）」，节奏在线，建议作者拍板。

uv run novel-editorial structure add <作品ID> chapter 第一章 --parent <卷ID>
# created <章ID-1> chapter 第一章

uv run novel-editorial structure add <作品ID> chapter 第二章 --parent <卷ID> --draft <草稿ID>
# created <章ID-2> chapter 第二章

uv run novel-editorial structure add <作品ID> section 第一篇 --parent <章ID-1>
# created <篇目ID> section 第一篇
```

树形输出带缩进；未完成节点无标记，挂草稿的节点行尾带草稿标题；`structure status` 标记后显示 `[已完成]`：

```bash
uv run novel-editorial structure list <作品ID>
# [卷] 第一卷（<卷ID>）
#   [章] 第一章（<章ID-1>）
#     [篇目] 第一篇（<篇目ID>）
#   [章] 第二章（<章ID-2>） <草稿标题>

uv run novel-editorial structure status <作品ID> <章ID-2> completed
# status updated: <章ID-2> completed

uv run novel-editorial structure list <作品ID>
# [卷] 第一卷（<卷ID>）
#   [章] 第一章（<章ID-1>）
#     [篇目] 第一篇（<篇目ID>）
#   [章] 第二章（<章ID-2>） [已完成] <草稿标题>
```

改名与大纲：`structure rename` 立即生效；`outline create` 首次落 v1，之后只能 `outline revise` 递增版本：

```bash
uv run novel-editorial structure rename <作品ID> <卷ID> 第一卷·雨夜
# renamed <卷ID>

uv run novel-editorial outline create <作品ID> --content "楔子：雨夜车站，钟停在十点差一刻。第一卷讲钟楼的来历，第一章埋下车站停运的伏笔。" --actor 作者
# outline v1 created

uv run novel-editorial outline revise <作品ID> --content "楔子：雨夜车站，钟停在十点差一刻。第一卷讲钟楼的来历，第二章揭晓车站停运的真相。" --reason 补充第二章悬念 --actor 责编
# outline v2 saved

uv run novel-editorial outline show <作品ID>
# outline v2：
# 楔子：雨夜车站，钟停在十点差一刻。第一卷讲钟楼的来历，第二章揭晓车站停运的真相。

uv run novel-editorial outline history <作品ID>
# v2 <时间戳> 责编 补充第二章悬念
# v1 <时间戳> 作者 initial
```

修订原因超 40 字时 history 截断补 `…`；大纲内容超 120 字时记忆包章纲截断：

```bash
uv run novel-editorial outline revise <作品ID> --content "楔子：雨夜车站，钟停在十点差一刻，没有人记得这座小站是什么时候废弃的。第一卷讲钟楼的来历，第一章埋下车站停运的伏笔，第二章揭晓钟声会把人带回二十年前的真相，第三章写沈夜在午夜钟声里发现站台尽头多出来的一班列车，第四章回到第一卷，把钟楼工匠的失踪案和车站废弃的真相缝在一起，结尾让整座车站连同钟声一起消失在雾里。" --reason 这一版把第三卷的线索也收进来了，还顺带调整了车站停运的时间线，让它和钟楼的来历对得上，同时把沈夜在午夜钟声里的戏份往前挪了一点。 --actor 作者
# outline v3 saved

uv run novel-editorial outline history <作品ID>
# v3 <时间戳> 作者 这一版把第三卷的线索也收进来了，还顺带调整了车站停运的时间线，让它和钟楼的来历对…
# v2 <时间戳> 责编 补充第二章悬念
# v1 <时间戳> 作者 initial

uv run novel-editorial memory pack <作品ID>
# 作品：《结构之书》（长篇）
# 简介：雨夜车站的悬疑长篇
# 章纲：楔子：雨夜车站，钟停在十点差一刻，没有人记得这座小站是什么时候废弃的。第一卷讲钟楼的来历，第一章埋下车站停运的伏笔，第二章揭晓钟声会把人带回二十年前的真相，第三章写沈夜在午夜钟声里发现站台尽头多出来的一班列车，第四章回到第一卷，把钟楼工匠的…
```

进度流转与可见性：`works status` 可传中文标签，输出规范三态；`works show` 的状态行在 title 之后、genre 之前，结构树在末尾（有结构才出现）：

```bash
uv run novel-editorial works status <作品ID> 已完成
# status updated: <作品ID> completed

uv run novel-editorial works show <作品ID>
# id: <作品ID>
# title: 结构之书
# 状态: 已完成
# genre: 长篇
# description: 雨夜车站的悬疑长篇
# band:
#   editor_in_chief: 总编
#   editor: 责编
#   writer: 写手
#   reviewer: 审稿
# 结构：
# [卷] 第一卷·雨夜（<卷ID>）
#   [章] 第一章（<章ID-1>）
#     [篇目] 第一篇（<篇目ID>）
#   [章] 第二章（<章ID-2>） [已完成] <草稿标题>
```

维护操作：`structure move` 换父级、`structure remove` 级联删除子树（输出删除的节点数），删完 `structure list` 变回无该子树：

```bash
uv run novel-editorial structure move <作品ID> <篇目ID> --parent <章ID-2>
# moved <篇目ID>

uv run novel-editorial structure remove <作品ID> <篇目ID>
# removed 1 node(s)

uv run novel-editorial structure list <作品ID>
# [卷] 第一卷·雨夜（<卷ID>）
#   [章] 第一章（<章ID-1>）
#   [章] 第二章（<章ID-2>） [已完成] <草稿标题>
```

空态与错误路径（mock 下实跑确认）：没有结构时 `structure list` 输出 `no structure`；没有大纲时 `outline show` / `outline history` 输出 `no outline`，`outline revise` 报业务错误（退出码 1）；`structure add` 传未知 kind、`structure move` 同时给 `--parent` 与 `--root`、`structure status` / `works status` 传非三态值、已有大纲再 `outline create` 都报用法错误（退出码 2）。

（`<作品ID>`、`<卷ID>`、`<章ID-*>`、`<篇目ID>`、`<草稿ID>` 与 `<时间戳>` 换成前面输出的真实值，每次运行不同；其余为 mock 下的真实输出。）

## 多写手并行（N14）

一部作品可以配置多位写手分章并行创作：大长篇不用等单写手串行写完，谁执笔、写的是哪一版，都在草稿里留痕。多写手只是「作品里多了几位写手 + 指定谁写」，仍然保持对话委托形态——没有任务队列、没有认领、没有超时惩罚，作者随时可以介入和拍板。

### agents add 与角色唯一性

- `agents add <作品ID> <role> <名字> [--personality <人设文本>]`：新增一位伙伴。`role` 收英文或中文：`writer` / `写手`、`editor_in_chief` / `总编`、`editor` / `责编`、`reviewer` / `审稿`。写手可以加任意多实例，其余角色作品内保持唯一（已有同角色再加报用法错误）；名字在作品内唯一，大小写不敏感（与既有伙伴名冲突报用法错误）。成功输出 `created agent <ID>: <名字> (<role>)`，例如 `created agent <ID>: 写手乙 (writer)`。
- 非法 role、重名、非写手角色重复都报用法错误（退出码 2）。
- `agents list <作品ID>`：按创建顺序输出 `[<role>] <名字>（<ID>）`。默认四名伙伴在同一事务建成（created_at 相同），相对顺序按 id 兜底；后加的角色一定排在它们之后。
- 名字是解析的主键：`draft generate` / `draft revise` 的 `--writer`、`memory note` / `memory notes` 的目标都先按 ID、再按名字（大小写不敏感）、最后按角色别名解析。重复名已被禁止，所以按名字解析不会歧义；角色别名（如「写手」）始终指向默认写手，也就是创建顺序的第一位写手。

### draft generate / draft revise 指定写手

- `draft generate <作品ID> [--title <标题>] [--writer <名字|ID>]`：`--writer` 指定执笔写手；不指定时走默认写手（创建顺序的第一位，与 N14 前完全一致）。指定非写手角色报用法错误（退出码 2），指定不存在的名字报业务错误（退出码 1）。
- `draft revise <草稿ID> [--reason <原因>] [--writer <名字|ID>]`：同理。缺省沿用草稿原写手（`writer_id`），显式传 `--writer` 时换人并更新留痕。
- 可见性：`draft list` 每行行尾带（写手名）；`draft show` 在标题行下输出 `writer: <写手名>` 行，执笔人一眼可辨。
- 草稿生成 / 修订通过质量门后的主动汇报仍以角色名发声（`写手` / `责编`），执笔人看 `draft list` / `draft show` 的写手名区分。

### 记忆隔离

- 每位写手的私有记忆按伙伴隔离：`memory note <作品ID> <名字|ID> --content <内容> --as <角色别名>` 的目标按名字定位；`--as` 仍只接受角色别名（作者 / 总编 / 主编 / 责编 / 写手 / 审稿），按角色做权限校验——写手角色可以写给任一位写手实例，例如 `--as 写手` 写给 `写手乙` 或 `写手丙` 都合法。
- `memory notes <作品ID> <名字|ID>` 按名查看某位写手的笔记；不带目标时列出全部伙伴的笔记，输出带 `[写手名]`。
- 生成 / 修订按指定写手构建记忆包，只注入该写手自己的私有笔记；`memory pack`（无 `--writer` 参数）默认展示默认写手的记忆包，行为与 N14 前逐字一致。

### 红线

- 不工单化：没有任务队列、没有认领状态机、没有超时惩罚，多写手只是「指定谁写」。
- 默认行为不变：不指定写手时，generate / revise / memory pack 与 N14 之前完全一致。
- 记忆与产出隔离：私有记忆按伙伴隔离，草稿留痕 `writer_id`，互不串写。
- 角色唯一性只对写手放开：总编 / 责编 / 审稿仍唯一。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n14\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n14\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 多写手之书 --genre 长篇 --description 两位写手并行创作的长篇
# created workspace <作品ID>: 多写手之书
```

加两位写手，再看班底（输出为 mock 下的真实结果；ID 每次运行不同，默认四名伙伴的相对顺序按 id 兜底、可能不同）：

```bash
uv run novel-editorial agents add <作品ID> 写手 写手乙
# created agent <ID-写手乙>: 写手乙 (writer)

uv run novel-editorial agents add <作品ID> 写手 写手丙 --personality "冷峻克制，擅长动作场面"
# created agent <ID-写手丙>: 写手丙 (writer)

uv run novel-editorial agents list <作品ID>
# [editor] 责编（<ID-1>）
# [writer] 写手（<ID-2>）
# [editor_in_chief] 总编（<ID-3>）
# [reviewer] 审稿（<ID-4>）
# [writer] 写手乙（<ID-5>）
# [writer] 写手丙（<ID-6>）
```

两位写手各生成一章，`draft list` 行尾带写手名，`draft show` 有 `writer:` 行：

```bash
uv run novel-editorial draft generate <作品ID> --title 第一章 --writer 写手乙
# draft <草稿ID-1> 第一章 now at v1
# awaiting decision: <草稿ID-1>
# 写手: 《第一章》初稿写完了，我按节奏收尾，先交给你过目。
# 责编: 《第一章》过了质量门，我试读了开头「（模拟回复）」，节奏在线，建议作者拍板。

uv run novel-editorial draft generate <作品ID> --title 第二章 --writer 写手丙
# draft <草稿ID-2> 第二章 now at v1
# awaiting decision: <草稿ID-2>
# 写手: 《第二章》初稿写完了，我按节奏收尾，先交给你过目。
# 责编: 《第二章》过了质量门，我试读了开头「（模拟回复）」，节奏在线，建议作者拍板。

uv run novel-editorial draft list <作品ID>
# <草稿ID-2>  第二章  v1  draft  （写手丙）
# <草稿ID-1>  第一章  v1  draft  （写手乙）

uv run novel-editorial draft show <草稿ID-1>
# 第一章 (v1, draft)
# writer: 写手乙
# reason: initial
# ---
# （模拟回复）

uv run novel-editorial draft show <草稿ID-2>
# 第二章 (v1, draft)
# writer: 写手丙
# reason: initial
# ---
# （模拟回复）
```

私有记忆按写手隔离：`memory note` 目标按名字定位、`--as` 用角色别名，`memory notes` 按名只能看到该写手自己的笔记：

```bash
uv run novel-editorial memory note <作品ID> 写手乙 --content 主角的左手小指缺了一截 --as 写手
# note added to 写手乙 by 写手

uv run novel-editorial memory note <作品ID> 写手丙 --content 第二卷的反转要埋在前三章 --as 写手
# note added to 写手丙 by 写手

uv run novel-editorial memory notes <作品ID> 写手乙
# <笔记ID-1> [写手乙] strength=100 主角的左手小指缺了一截

uv run novel-editorial memory notes <作品ID> 写手丙
# <笔记ID-2> [写手丙] strength=100 第二卷的反转要埋在前三章

uv run novel-editorial memory notes <作品ID>
# <笔记ID-1> [写手乙] strength=100 主角的左手小指缺了一截
# <笔记ID-2> [写手丙] strength=100 第二卷的反转要埋在前三章
```

不指定 `--writer` 时仍走默认写手（第一位，也就是班底里的「写手」），行为与 N14 前一致：

```bash
uv run novel-editorial draft generate <作品ID> --title 第三章
# draft <草稿ID-3> 第三章 now at v1
# awaiting decision: <草稿ID-3>
# 写手: 《第三章》初稿写完了，我按节奏收尾，先交给你过目。
# 责编: 《第三章》过了质量门，我试读了开头「（模拟回复）」，节奏在线，建议作者拍板。

uv run novel-editorial draft list <作品ID>
# <草稿ID-3>  第三章  v1  draft  （写手）
# <草稿ID-2>  第二章  v1  draft  （写手丙）
# <草稿ID-1>  第一章  v1  draft  （写手乙）

uv run novel-editorial draft show <草稿ID-3>
# 第三章 (v1, draft)
# writer: 写手
# reason: initial
# ---
# （模拟回复）
```

（`<作品ID>`、`<ID-*>`、`<草稿ID-*>` 与 `<笔记ID-*>` 换成前面输出的真实值，每次运行不同；默认四名伙伴同一事务建成、created_at 相同，`agents list` 里它们的相对顺序按 id 兜底；其余为 mock 下的真实输出。）

退出码验证：`agents add` 的非法 role、重名、非写手角色重复都报用法错误（退出码 2）；`draft generate` / `draft revise` 的 `--writer` 指定非写手角色报用法错误（退出码 2），指定不存在的名字报业务错误（退出码 1）。

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

## 记忆衰减与归档（N17）

伙伴的私有笔记不再无限堆叠：没人想起来的笔记会随时间自然变淡，弱到一定程度就可以归档；归档的笔记默认不出现在检索、笔记清单和写作记忆包里，但随时可以无损恢复。衰减只是改变权重，归档只是藏起来，两者都不删除内容——真正的删除只有 `memory delete`。

### 衰减模型

每条笔记有一个强度值 `strength`，范围 0–100：

- 新笔记初始 `strength=100`；
- 距上次访问每过一个整天，`strength` 按 `NOVEL_MEMORY_DECAY_PER_DAY`（默认 `5`）线性下降，下限 0；
- 检索命中或 `memory remember` 会保鲜：`strength` 增加 `NOVEL_MEMORY_REHEARSAL_BOOST`（默认 `25`），上限 100，同时把「上次访问时间」更新为当前时刻；
- 归档候选 = 活跃笔记中当前有效强度 ≤ `NOVEL_MEMORY_ARCHIVE_THRESHOLD`（默认 `20`）的笔记。

有效强度按整天折算，不满一天的部分不计；`memory decay` 会把上次访问时间推进到执行时刻，所以同一天重复执行不会再衰减（幂等）。

三项配置的优先级与其他配置一致：环境变量 > `config.toml` > 内置默认值。写进 `config.toml` 用的是 `[defaults]` 同名键：

```toml
[defaults]
memory_decay_per_day = 5
memory_rehearsal_boost = 25
memory_archive_threshold = 20
```

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `NOVEL_MEMORY_DECAY_PER_DAY` | 每整天的强度衰减量 | `5` |
| `NOVEL_MEMORY_REHEARSAL_BOOST` | 检索命中 / remember 的保鲜增量 | `25` |
| `NOVEL_MEMORY_ARCHIVE_THRESHOLD` | 归档候选的强度阈值 | `20` |

三项都必须是非负整数，阈值还不得超过 100；非法值报配置错误（退出码 1）。

### 命令

- `memory decay <作品ID>`：对活跃笔记应用衰减，逐条输出 `笔记ID: 旧强度 -> 新强度`；没有笔记变化时输出 `no decay this time`。
- `memory remember <作品ID> <笔记ID>`：保鲜一条笔记，输出 `笔记ID strength=新强度`；已归档的笔记报用法错误（退出码 2），未知笔记报业务错误（退出码 1）。
- `memory archive <作品ID> [笔记ID...] [--candidates]`：显式传笔记 ID 直接归档（不限强度，供作者整理）；加 `--candidates` 则归档全部阈值候选。成功输出 `archived N note(s)`；没有候选时输出 `no archive candidates`；既不传 ID 也不加 `--candidates` 报用法错误（退出码 2），`--candidates` 与显式笔记 ID 混用同样报用法错误。
- `memory restore <作品ID> <笔记ID...>`：恢复已归档笔记，输出 `restored N note(s)`；`strength` 与上次访问时间保持原值，不额外加权；未知笔记报业务错误（退出码 1）。
- `memory notes <作品ID> [伙伴别名] [--include-archived]`：默认只列活跃笔记，输出 `笔记ID [伙伴] strength=N 内容`；加 `--include-archived` 后已归档笔记也会列出，行尾带【归档】标记。

### 归档语义

归档只置归档时间戳（`archived_at`）留痕，内容原样保留：

- `memory search`、`memory notes`、`memory pack` 默认都看不到已归档笔记；
- `memory notes --include-archived` 可以查看，行尾带【归档】标记；
- `memory restore` 随时恢复，恢复后重新出现在检索与记忆包里；
- 归档不删除内容，`memory delete` 仍是唯一真正删除的通道，语义不变。

### 红线

- 衰减只是权重不是删除：只改变 `strength`、排序与默认可见性，绝不自动删内容；
- 归档可逆且留痕：`archived_at` 记录归档时间，恢复无损；
- 衰减不阻塞：检索与记忆包只按强度排序、默认排除归档，但永不因强度低而阻断注入或检索；检索保鲜失败只向 stderr 告警，检索结果不受影响。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n17\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n17\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 记忆之书 --genre 悬疑
# created workspace <作品ID>: 记忆之书
```

以写手身份写两条笔记：

```bash
uv run novel-editorial memory note <作品ID> 写手 --content 主角害怕旧车站的钟声 --as 写手
# note added to 写手 by 写手

uv run novel-editorial memory note <作品ID> 写手 --content 旧车站的钟每天慢三分钟 --as 写手
# note added to 写手 by 写手
```

`memory notes` 能看到两条笔记和各自的笔记 ID（ID 每次运行不同）：

```bash
uv run novel-editorial memory notes <作品ID>
# <笔记ID-1> [写手] strength=100 主角害怕旧车站的钟声
# <笔记ID-2> [写手] strength=100 旧车站的钟每天慢三分钟
```

为了演示跨天衰减，把两条笔记的「上次访问时间」拨到 20 天前（真实使用中时间自然流逝，不需要这一步）：

```bash
uv run python -c '
import os, sqlite3, pathlib
from datetime import UTC, datetime, timedelta
db = pathlib.Path(os.environ["NOVEL_DATA_DIR"]) / "works" / "<作品ID>" / "data.db"
conn = sqlite3.connect(db)
old = (datetime.now(UTC) - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
conn.execute("UPDATE agent_memories SET last_accessed_at = ?", (old,))
conn.commit()
'
```

跑 `memory decay`：20 个整天 × 每天 5，两条都从 100 衰减到下限 0；立刻再跑一次没有变化（幂等）：

```bash
uv run novel-editorial memory decay <作品ID>
# <笔记ID-1>: 100 -> 0
# <笔记ID-2>: 100 -> 0

uv run novel-editorial memory decay <作品ID>
# no decay this time
```

强度 0 低于默认阈值 20，两条笔记都是归档候选，`memory archive --candidates` 把它们全部归档：

```bash
uv run novel-editorial memory archive <作品ID> --candidates
# archived 2 note(s)
```

归档后，检索、笔记清单和写作记忆包默认都看不到这两条：

```bash
uv run novel-editorial memory search <作品ID> 旧车站
# no matches

uv run novel-editorial memory notes <作品ID>
# no memory notes yet

uv run novel-editorial memory pack <作品ID>
# 作品：《记忆之书》（悬疑）
# 简介：
# 章纲：暂无（占位）
```

`memory notes --include-archived` 能查到它们，行尾带【归档】标记，`strength` 保持 0：

```bash
uv run novel-editorial memory notes <作品ID> --include-archived
# <笔记ID-1> [写手] strength=0 【归档】 主角害怕旧车站的钟声
# <笔记ID-2> [写手] strength=0 【归档】 旧车站的钟每天慢三分钟
```

恢复后重新可见，`strength` 与上次访问时间保持原值：

```bash
uv run novel-editorial memory restore <作品ID> <笔记ID-1> <笔记ID-2>
# restored 2 note(s)

uv run novel-editorial memory notes <作品ID>
# <笔记ID-1> [写手] strength=0 主角害怕旧车站的钟声
# <笔记ID-2> [写手] strength=0 旧车站的钟每天慢三分钟
```

`memory remember` 保鲜一条（0 + 25 = 25）；检索命中也会自动保鲜，搜索「钟声」命中第一条后，它的 `strength` 从 25 升到 50：

```bash
uv run novel-editorial memory remember <作品ID> <笔记ID-1>
# <笔记ID-1> strength=25

uv run novel-editorial memory search <作品ID> 钟声
# [笔记] 主角害怕旧车站的钟声（来源: 写手）

uv run novel-editorial memory notes <作品ID>
# <笔记ID-1> [写手] strength=50 主角害怕旧车站的钟声
# <笔记ID-2> [写手] strength=0 旧车站的钟每天慢三分钟
```

（`<作品ID>` 与 `<笔记ID-*>` 换成前面输出的真实 ID，每次运行不同；其余为 mock 下的真实输出。）

## 作品设定库（N5）

作品设定（人物、关系、时间线、世界观）可以条目化沉淀，每条设定从 v1 开始，修订一次版本递增一次，来源、原因、操作者逐版本留痕——随时知道一条设定从哪来、改过什么、现在是什么。设定库只记录，不自动改写正文；也没有「先建设定才能写」的关卡，创作路径完全不受影响。

### kind 与版本语义

- 四种 kind：`人物`、`关系`、`时间线`、`世界观`（内部为 `character` / `relation` / `timeline` / `world`），CLI 统一用中文标签；kind 只是标签，不构成流程关卡，不按体裁特化。
- 新条目从 v1 起：`setting add` 落 v1，同时写入第一条版本记录（原因固定 `initial`，操作者取来源）。
- 修订版本递增：每次 `setting revise` 版本 +1、当前内容同步更新；每条修订必须有原因（`--reason`）与操作者（`--actor`），两者非空——来源可溯是红线，任何版本都说得清「谁、为什么、改成了什么」。
- 来源：`setting add` 用 `--source` 记录设定出处（默认「作者」），v1 的操作者即来源；之后每个版本的操作者由 `--actor` 单独留痕（默认「作者」）。

### 命令

- `setting add <作品ID> --kind <人物|关系|时间线|世界观> --name <名称> --content <内容> [--source <来源>]`：新建设定条目并落 v1，成功输出 `added <设定ID> [人物] 沈夜 v1`。名称必须非空且单行，内容与来源必须非空；未知 kind 或空值报用法错误（退出码 2），作品不存在报业务错误（退出码 1）。
- `setting list <作品ID> [--kind <人物|关系|时间线|世界观>]`：按创建顺序列出设定，输出 `<设定ID> [人物] 沈夜 v1 <内容>`；`--kind` 只列指定标签；没有设定时输出 `no settings yet`。
- `setting show <作品ID> <设定ID>`：显示名称、标签、当前版本、来源与当前内容，输出为 `沈夜 [人物] v1`、`source: 作者`、`---`、内容四行；设定不存在报业务错误（退出码 1）。
- `setting revise <作品ID> <设定ID> --content <新内容> --reason <原因> [--actor <操作者>]`：显式修订，版本 +1，成功输出 `revised <设定ID> 沈夜 v2`；内容、原因、操作者必须非空，空值报用法错误（退出码 2），设定不存在报业务错误（退出码 1）。
- `setting history <作品ID> <设定ID>`：逐版本输出 `v1 作者 initial <内容>`，版本升序，v1 的原因固定 `initial`；设定不存在报业务错误（退出码 1）。

内容含空格时用引号包起来（PowerShell 与 bash 写法一致），例如 `--content "1998 年车站停运，钟永远停在十点差一刻。"`；不带引号的参数遇空格会被拆开。命令退出码沿用全局语义：`0` 成功、`1` 业务错误、`2` 用法错误（见「退出码」一节）。

### 检索 [设定] 层

`memory search <作品ID> <关键词>` 与 `inspect <作品ID> <关键词>` 都会检索设定层：对设定的名称与内容做子串匹配，命中后输出 `[设定] <标签>：<名称>——<摘要>（来源: <来源> v<版本>）`，按更新时间升序、id 兜底；两条命令的设定层输出完全一致。检索只读，不依赖 FTS 可用性，也不影响创作流程。

### 红线

- 沉淀不是前置：设定库随创作自然沉淀，不建设定不影响写稿、修订与过稿，没有一条流程要求先建设定。
- 只记录不改写：设定条目与版本只做记录，绝不自动改写正文、不绕过角色判断；修订是显式动作，每次都要原因与操作者。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n5\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n5\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 设定之书 --genre 悬疑
# created workspace <作品ID>: 设定之书
```

沉淀一条人物设定和一条时间线设定（来源都留痕）：

```bash
uv run novel-editorial setting add <作品ID> --kind 人物 --name 沈夜 --content 二十岁出头的古董修复师，最怕旧车站的钟声。 --source 作者
# added <设定ID-1> [人物] 沈夜 v1

uv run novel-editorial setting add <作品ID> --kind 时间线 --name 旧车站 --content "1998 年车站停运，钟永远停在十点差一刻。" --source 第一章手稿
# added <设定ID-2> [时间线] 旧车站 v1
```

`setting list` 按创建顺序列出两条设定，每条带当前版本与内容：

```bash
uv run novel-editorial setting list <作品ID>
# <设定ID-1> [人物] 沈夜 v1 二十岁出头的古董修复师，最怕旧车站的钟声。
# <设定ID-2> [时间线] 旧车站 v1 1998 年车站停运，钟永远停在十点差一刻。
```

`setting show` 显示当前版本、来源与内容：

```bash
uv run novel-editorial setting show <作品ID> <设定ID-1>
# 沈夜 [人物] v1
# source: 作者
# ---
# 二十岁出头的古董修复师，最怕旧车站的钟声。
```

修订人物设定：版本从 v1 升到 v2，原因与操作者必须留下：

```bash
uv run novel-editorial setting revise <作品ID> <设定ID-1> --content "二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。" --reason 第二章补充人物背景 --actor 作者
# revised <设定ID-1> 沈夜 v2
```

`setting history` 逐版本可溯：v1 是来源初版，v2 带原因与操作者：

```bash
uv run novel-editorial setting history <作品ID> <设定ID-1>
# v1 作者 initial 二十岁出头的古董修复师，最怕旧车站的钟声。
# v2 作者 第二章补充人物背景 二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。
```

`memory search` 按内容命中设定层，结果带来源与版本号；`inspect` 输出相同：

```bash
uv run novel-editorial memory search <作品ID> 车站
# [设定] 时间线：旧车站——1998 年车站停运，钟永远停在十点差一刻。（来源: 第一章手稿 v1）
# [设定] 人物：沈夜——二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者 v2）

uv run novel-editorial inspect <作品ID> 车站
# [设定] 时间线：旧车站——1998 年车站停运，钟永远停在十点差一刻。（来源: 第一章手稿 v1）
# [设定] 人物：沈夜——二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者 v2）
```

（`<作品ID>` 与 `<设定ID-*>` 换成前面输出的真实 ID，每次运行不同；其余为 mock 下的真实输出。）

### 设定影响分析（N18）

改动一条设定之前，先跑 `setting impact` 看它牵动了哪些内容：草稿正文版本、对话、意见、伏笔线索、伙伴笔记、其它设定条目都会按关键词扫一遍。输出是只读报告——只回答「哪些层、哪些条目、为什么命中」，不代笔、不构成任何创作前置。设定修订后同一命令仍可跑，报告自动按新版本内容重新检索。

#### 命令

- `setting impact <作品ID> <设定ID> [--limit N] [--verbose]`：只读报告一条设定牵动的层。
  - 无影响输出一行：`no impact found for <设定名> v<N>`。
  - 有影响先输出标题行 `impact for <设定名> v<N>（共 M 条）：`，再逐行输出 `[层标签] <来源>：<片段>`；`M` 是命中总数，`--limit` 只截断展示行数、不改总数。
  - 层顺序固定：版本 → 对话 → 意见 → 线索 → 笔记 → 设定；层内按更新时间/创建时间倒序。
  - `--limit` 默认 `20`；小于 `1` 报用法错误（退出码 `2`）。设定或作品不存在报业务错误（退出码 `1`）。
  - `--verbose` 在标题前先输出一行 `keywords: ...`（关键词用「、」连接），便于排查为什么命中或没命中。

#### 关键词口径

- 关键词集 = 设定名称（整体一个关键词）+ 内容折叠片段：内容按空白折叠后切出的词块，只保留 ≥2 字的，去重、按长度降序取前 5；没有合格词块时退到折叠内容前 20 字。
- 命中判定是大小写不敏感的子串匹配；参与检索的层：版本正文（草稿全部版本）、对话、意见、伏笔线索、活跃伙伴笔记、其它设定条目（名称或内容）。
- 排除自身条目：自己的名称与内容不会出现在报告里，自身历史版本也不参与检索；归档笔记不参与。
- 命中片段折叠空白并截断 60 字，超长末尾补 `…`。

#### 红线

- 只报告不代笔：影响分析只输出「哪些层、哪些条目、为什么命中」，绝不自动改写正文、不绕过角色判断；修订仍是显式动作。
- 不阻塞：impact 是纯只读检索命令，不构成任何创作前置；单层查询失败只向 stderr 告警并跳过该层，报告不整体失败，其它命令不受影响。

#### 影响分析示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现，用独立数据目录，可单独从头复现。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n18\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n18\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 影响之书 --genre 悬疑
# created workspace <作品ID>: 影响之书

uv run novel-editorial setting add <作品ID> --kind 人物 --name 钟声 --content "雨夜的旧城 回荡着钟声" --source 作者
# added <设定ID-1> [人物] 钟声 v1
```

生成第一章草稿，再给第一章补一条含「钟声」的正文版本。mock 模式下写手正文固定为「（模拟回复）」，不会命中关键词，所以这一步用项目 API 直接落一条含「钟声」的正文版本（与测试用例同一口径）；配了真实 key 后正文由模型生成，命中与否取决于正文本身。bash 用 heredoc：

```bash
uv run novel-editorial draft generate <作品ID> --title 第一章
# draft <草稿ID> 第一章 now at v1
# awaiting decision: <草稿ID>
# 写手: 《第一章》初稿写完了，我按节奏收尾，先交给你过目。
# 责编: 《第一章》过了质量门，我试读了开头「（模拟回复）」，节奏在线，建议作者拍板。

uv run python - <<'PY'
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft, DraftVersion

settings = load_settings()
db = DB(settings)
db.init_schema()
workspace_id = "<作品ID>"
draft_id = "<草稿ID>"
with db.workspace_session(workspace_id) as session:
    draft = session.query(Draft).filter_by(id=draft_id).first()
    draft.current_version = 2
    session.add(DraftVersion(draft_id=draft_id, version=2, content="雨夜的旧城，钟声在十点差一刻准时响起，回荡在空无一人的站台。", reason="示例注入"))
    session.commit()
print("draft version injected: 第一章 v2")
PY
# draft version injected: 第一章 v2
```

PowerShell 用户可把上面 heredoc 里的内容存成临时脚本后 `uv run python <脚本路径>` 运行。接着写对话、意见、伏笔、笔记和另一条设定，全部走 CLI：

```bash
uv run novel-editorial talk send <作品ID> "雨夜的旧城，氛围要再压一压。"
# 作者: 雨夜的旧城，氛围要再压一压。
# 总编: （模拟回复）
# 责编: 我想先确认一下：这部作品的主角动机和核心冲突，咱们还没对齐吧？这个定不下来，后面每一章都会飘。
# 总编: 这部作品的方向还没定：整体基调、核心冲突，咱们先把这些捋清楚再动笔。

uv run novel-editorial review add <草稿ID> --from 责编 --content "钟声段落的雨夜氛围再打磨"
# review added by 责编: 钟声段落的雨夜氛围再打磨

uv run novel-editorial plot plant <作品ID> --kind foreshadow --content "钟声是解开旧城雨夜之谜的钥匙"
# planted <线索ID> [伏笔] 钟声是解开旧城雨夜之谜的钥匙
# 审稿: 线索「钟声是解开旧城雨夜之谜的钥匙」埋下了。我记进时间线，回头逐章对照，别让它断在半路。

uv run novel-editorial memory note <作品ID> 写手 --content "钟声响起时注意旧城雨夜的节奏" --as 写手
# note added to 写手 by 写手

uv run novel-editorial setting add <作品ID> --kind 世界观 --name 旧城 --content "钟声会改变旧城的时间流向" --source 作者
# added <设定ID-2> [世界观] 旧城 v1
```

第一次 impact：六层全命中，共 7 条。对话层有两条——作者消息命中内容片段「雨夜的旧城」，审稿的埋线回复命中名称「钟声」：

```bash
uv run novel-editorial setting impact <作品ID> <设定ID-1>
# impact for 钟声 v1（共 7 条）：
# [版本] 第一章 v2：雨夜的旧城，钟声在十点差一刻准时响起，回荡在空无一人的站台。
# [对话] 审稿：线索「钟声是解开旧城雨夜之谜的钥匙」埋下了。我记进时间线，回头逐章对照，别让它断在半路。
# [对话] 作者：雨夜的旧城，氛围要再压一压。
# [意见] 责编 的意见：钟声段落的雨夜氛围再打磨
# [线索] 伏笔：伏笔：钟声是解开旧城雨夜之谜的钥匙
# [笔记] 写手：钟声响起时注意旧城雨夜的节奏
# [设定] 旧城（世界观）：钟声会改变旧城的时间流向
```

修订设定后 impact 仍可跑：内容从「雨夜的旧城 回荡着钟声」改为「晨光 山岭」，名称仍是「钟声」，关键词集变成「钟声、晨光、山岭」。只命中旧内容片段的引用会消失（v1 的 7 条变 v2 的 6 条，作者那条「雨夜的旧城」不再计入），命中名称「钟声」的引用全部保留：

```bash
uv run novel-editorial setting revise <作品ID> <设定ID-1> --content "晨光 山岭" --reason 旧城线重写 --actor 作者
# revised <设定ID-1> 钟声 v2

uv run novel-editorial setting impact <作品ID> <设定ID-1>
# impact for 钟声 v2（共 6 条）：
# [版本] 第一章 v2：雨夜的旧城，钟声在十点差一刻准时响起，回荡在空无一人的站台。
# [对话] 审稿：线索「钟声是解开旧城雨夜之谜的钥匙」埋下了。我记进时间线，回头逐章对照，别让它断在半路。
# [意见] 责编 的意见：钟声段落的雨夜氛围再打磨
# [线索] 伏笔：伏笔：钟声是解开旧城雨夜之谜的钥匙
# [笔记] 写手：钟声响起时注意旧城雨夜的节奏
# [设定] 旧城（世界观）：钟声会改变旧城的时间流向
```

新建一条没有任何引用的设定，impact 输出空态（退出码 0）：

```bash
uv run novel-editorial setting add <作品ID> --kind 时间线 --name 灯塔 --content "灯塔 渔船" --source 作者
# added <设定ID-3> [时间线] 灯塔 v1

uv run novel-editorial setting impact <作品ID> <设定ID-3>
# no impact found for 灯塔 v1
```

`--verbose` 在标题前输出关键词集，无影响时也一样先打印 keywords 再打印 no impact：

```bash
uv run novel-editorial setting impact <作品ID> <设定ID-3> --verbose
# keywords: 灯塔、渔船
# no impact found for 灯塔 v1

uv run novel-editorial setting impact <作品ID> <设定ID-1> --verbose
# keywords: 钟声、晨光、山岭
# impact for 钟声 v2（共 6 条）：
# [版本] 第一章 v2：雨夜的旧城，钟声在十点差一刻准时响起，回荡在空无一人的站台。
# [对话] 审稿：线索「钟声是解开旧城雨夜之谜的钥匙」埋下了。我记进时间线，回头逐章对照，别让它断在半路。
# [意见] 责编 的意见：钟声段落的雨夜氛围再打磨
# [线索] 伏笔：伏笔：钟声是解开旧城雨夜之谜的钥匙
# [笔记] 写手：钟声响起时注意旧城雨夜的节奏
# [设定] 旧城（世界观）：钟声会改变旧城的时间流向
```

`--limit` 只截断展示行数，标题里的总数不变：

```bash
uv run novel-editorial setting impact <作品ID> <设定ID-1> --limit 2
# impact for 钟声 v2（共 6 条）：
# [版本] 第一章 v2：雨夜的旧城，钟声在十点差一刻准时响起，回荡在空无一人的站台。
# [对话] 审稿：线索「钟声是解开旧城雨夜之谜的钥匙」埋下了。我记进时间线，回头逐章对照，别让它断在半路。
```

退出码：`--limit 0` 报用法错误（退出码 2）；未知设定报业务错误（退出码 1）：

```bash
uv run novel-editorial setting impact <作品ID> <设定ID-1> --limit 0
# Error: limit must be at least 1, got 0（退出码 2）

uv run novel-editorial setting impact <作品ID> <不存在的设定ID>
# Error: setting not found: <不存在的设定ID>（退出码 1）
```

（`<作品ID>`、`<设定ID-*>`、`<草稿ID>` 与 `<线索ID>` 换成前面输出的真实 ID，每次运行不同；时间戳与 stderr 日志已省略；其余为 mock 下的真实输出。）

## 知识管家（N6）

设定沉淀进库之后不能只躺在库里：写手动笔和编辑审稿时应该自动看到当前版本，改过的地方要在事件流里有迹可循，陈旧条目与同名矛盾候选要被指出来由作者判断。N6 就是把这条分发闭环补上——`memory pack` 与编辑视图自动带「设定：」段，修订在 `events list` 留痕，`setting check` 负责只读报告。

### 分发语义

- 写手记忆包（`memory pack`）与编辑视图（`memory view --as 责编` / `--as 总编`）自动带「设定：」段，放在私有记忆之后、悬置线索之前；每行格式 `- [人物] 沈夜 v2 当前内容（来源: 作者）`。
- 行序固定：kind 固定序（人物→关系→时间线→世界观），同 kind 按更新时间升序、id 兜底；无设定条目时整段不出现，记忆包与视图其余部分照常。
- 分发永远用当前版本：记忆包、编辑视图、检索一律读 `current_version` 的内容，旧版本只留在 `setting history` 可溯，绝不分发历史版本。
- 检索 [设定] 层同源：`memory search` 与 `inspect` 命中设定层时输出与 N5 相同的 `[设定] <标签>：<名称>——<摘要>（来源: <来源> v<版本>）`，版本号即当前版本；分发、视图、检索三路读的是同一份当前内容。

### 修订事件留痕

`setting revise` 在版本落库后追加一条 system 事件（复用既有事件流，不新增事件类型），payload 为：

```json
{"kind": "setting_revised", "setting_id": "<设定ID>", "name": "沈夜", "version": 2, "actor": "作者", "reason": "第二章补充人物背景"}
```

`events list` 可以看到该事件，行格式 `[system] <操作者> <payload>`；payload 超过 80 字符时列表截断显示（末尾 `...`），完整内容留在事件流内。事件写入失败只向 stderr 告警，不阻塞修订本身。

### setting check

- `setting check <作品ID>`：只读报告，输出统计行 `settings: N entries (M revised)`（N 为总条目数，M 为已修订条目数，即 `current_version > 1`）。
- 存在已修订条目时列出陈旧列表：`- 沈夜（人物）v2 <当前内容>（来源: 作者）—— 已修订，旧版本见 history`。
- 同名条目（任意 kind）按名称分组列出矛盾候选：`- 「沈夜」：人物 v2 与 世界观 v1 —— 同名条目，请确认是否矛盾`；同名条目即使 kind 不同也会被识别。
- 没有陈旧也没有同名冲突时输出单行：`settings: N entries (M revised)；同名冲突：无`（空库为 `settings: 0 entries (0 revised)；同名冲突：无`）。
- 退出码沿用全局语义：成功 `0`，作品不存在等业务错误 `1`，用法错误 `2`（如 `setting add` 传未知 kind）。

### 红线

- 沉淀不是前置：不建设定条目不影响写稿、修订与过稿；无设定时记忆包与编辑视图照常，只是没有「设定：」段。
- 只报告不改写：`setting check` 只输出报告供作者判断，不自动改设定、不改正文、不绕过角色判断；修订仍是显式动作。
- 分发用当前版本：记忆包、编辑视图、检索只读 `current_version`，旧版本只留在 history 可溯，绝不用陈旧版本污染创作上下文。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n6\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n6\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 设定之书 --genre 悬疑
# created workspace <作品ID>: 设定之书
```

沉淀一条人物设定，再沉淀一条世界观设定，故意同名（制造同名冲突候选）：

```bash
uv run novel-editorial setting add <作品ID> --kind 人物 --name 沈夜 --content 二十岁出头的古董修复师，最怕旧车站的钟声。 --source 作者
# added <设定ID-1> [人物] 沈夜 v1

uv run novel-editorial setting add <作品ID> --kind 世界观 --name 沈夜 --content 全城只有一座钟楼，钟声在午夜后会把人带回二十年前。 --source 作者
# added <设定ID-2> [世界观] 沈夜 v1
```

修订人物设定：版本从 v1 升到 v2：

```bash
uv run novel-editorial setting revise <作品ID> <设定ID-1> --content "二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。" --reason 第二章补充人物背景 --actor 作者
# revised <设定ID-1> 沈夜 v2
```

写手记忆包自动带「设定：」段，人物显示的是 v2 当前内容，kind 固定序（人物先于世界观）：

```bash
uv run novel-editorial memory pack <作品ID>
# 作品：《设定之书》（悬疑）
# 简介：
# 章纲：暂无（占位）
# 设定：
# - [人物] 沈夜 v2 二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者）
# - [世界观] 沈夜 v1 全城只有一座钟楼，钟声在午夜后会把人带回二十年前。（来源: 作者）
```

责编视图同样带设定段，内容与记忆包一致：

```bash
uv run novel-editorial memory view <作品ID> --as 责编
# 作品档案：
# 标题：《设定之书》
# 体裁：悬疑
# 简介：
# 最近对话：
# （暂无）
# 设定：
# - [人物] 沈夜 v2 二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者）
# - [世界观] 沈夜 v1 全城只有一座钟楼，钟声在午夜后会把人带回二十年前。（来源: 作者）
```

修订在事件流留痕，`events list` 可见 `[system]` 事件（payload 超 80 字符时截断显示）：

```bash
uv run novel-editorial events list <作品ID>
# <时间戳> [system] 作者 {"kind": "setting_revised", "setting_id": "<设定ID-1>", "n...
```

`setting check` 输出统计、陈旧列表与同名冲突候选：

```bash
uv run novel-editorial setting check <作品ID>
# settings: 2 entries (1 revised)
# 陈旧（已修订）：
# - 沈夜（人物）v2 二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者）—— 已修订，旧版本见 history
# 同名冲突：
# - 「沈夜」：人物 v2 与 世界观 v1 —— 同名条目，请确认是否矛盾
```

检索 [设定] 层与分发同源，版本号为当前版本；`inspect` 输出相同：

```bash
uv run novel-editorial memory search <作品ID> 车站
# [设定] 人物：沈夜——二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者 v2）

uv run novel-editorial inspect <作品ID> 车站
# [设定] 人物：沈夜——二十岁出头的古董修复师，能修好任何钟，唯独不肯靠近旧车站。（来源: 作者 v2）
```

不建设定也不影响创作：新作品没有任何设定条目时，记忆包没有「设定：」段，`setting check` 输出空态单行（退出码 0）：

```bash
uv run novel-editorial works create 空态之书 --genre 悬疑
# created workspace <作品ID>: 空态之书

uv run novel-editorial memory pack <作品ID>
# 作品：《空态之书》（悬疑）
# 简介：
# 章纲：暂无（占位）

uv run novel-editorial setting check <作品ID>
# settings: 0 entries (0 revised)；同名冲突：无
```

退出码验证：`setting check` 正常完成退出码 0；对不存在的作品运行 `setting check` 报业务错误（退出码 1）；`setting add` 传未知 kind 报用法错误（退出码 2）。

（`<作品ID>`、`<设定ID-*>` 与 `<时间戳>` 换成前面输出的真实值，每次运行不同；其余为 mock 下的真实输出。）

## 语义记忆检索（N7）

`memory search` 除了按关键词子串命中，还能按「意思相近」联想记忆片段：私有笔记与设定条目在字面查不到时，仍可能凭语义相似被想起。语义检索是显式增强——不加 `--semantic` 时默认输出完全不变，加了才在关键词结果之后追加语义命中。

### 两档后端能力边界

| 后端 | 是否默认 | 行为 | 适用 |
| --- | --- | --- | --- |
| `local` | 是 | 字符 n-gram（n=1..3）哈希桶向量 + 余弦相似度；离线确定性（同文本同向量），零外部依赖；是字面近义近似，能捕捉词序变化与字形近义 | 默认零配置、可离线复现 |
| `api` | 否 | OpenAI 兼容 `/embeddings`，真语义；复用 `NOVEL_LLM_BASE_URL` 与 `NOVEL_LLM_API_KEY` | 显式配置 `embedding_model` 后启用 |

两档共用同一张向量索引表与检索服务：换后端后索引里的向量来自不同算法，需要 `memory reindex` 重建才能正确检索。local 的「语义」是字面近义近似，不是语言模型级语义——它靠字符重叠打分，比如「雨夜归乡」能靠近「雨夜回乡」，但完全换了写法就不保证命中。

### 配置

四项配置的优先级与其他配置一致：环境变量 > `config.toml [defaults]` 同名键 > 内置默认值。

| 变量 | 作用 | 默认值 | 校验 |
| --- | --- | --- | --- |
| `NOVEL_EMBEDDING_BACKEND` | 嵌入后端（`local` / `api`） | `local` | 只允许 `local` 与 `api`，其余报配置错误（退出码 1） |
| `NOVEL_EMBEDDING_MODEL` | api 后端模型名；api 后端必须显式配置 | 空 | api 后端为空时语义功能降级为空结果并在 stderr 告警（命令退出码不变） |
| `NOVEL_EMBEDDING_DIM` | local 后端向量维度 | `256` | 正整数 32–4096 |
| `NOVEL_EMBEDDING_TOP_K` | 单次语义检索返回上限 | `5` | 正整数 1–50 |

写进 `config.toml`：

```toml
[defaults]
embedding_backend = "local"
embedding_model = ""
embedding_dim = 256
embedding_top_k = 5
```

切换 api 后端的示例（PowerShell 用 `$env:NOVEL_EMBEDDING_BACKEND = "api"` 等写法）：

```bash
export NOVEL_EMBEDDING_BACKEND=api
export NOVEL_EMBEDDING_MODEL="text-embedding-3-small"
# 复用 NOVEL_LLM_BASE_URL / NOVEL_LLM_API_KEY 指向 OpenAI 兼容 /embeddings 接口
```

### 语义检索行为

`memory search <作品ID> <关键词> --semantic`：

- 默认输出不变：不加 `--semantic` 与之前完全一致；加了之后关键词结果原样输出，语义命中追加在最后。
- 行格式沿用引用式：`[笔记] <片段>（来源: <伙伴>）[语义 0.87]`、`[设定] <标签>：<名称>——<片段>（来源: <来源> v<版本>）[语义 0.91]`，相似度保留两位小数。
- 按相似度降序排列；字面命中（笔记内容或设定名称含关键词）不重复输出。
- 字面无命中、语义也无命中时仍输出 `no matches`（退出码 0）。
- 检索层：笔记（当前内容）与设定条目（当前版本内容）；对话、意见、正文版本等层暂不参与。

### memory reindex

`memory reindex <作品ID>` 遍历本作品的笔记与设定，把当前内容全部重新嵌入，输出 `reindexed N entries`：

- 幂等：重复执行结果一致（第二次仍是同样的 `N`，不会重复计数）。
- 覆盖全部笔记（含已归档），但查询时归档笔记与已删除来源不参与语义命中——与关键词检索口径一致。
- 笔记增删改、设定增改时索引自动增量同步，正常使用不需要手动 reindex；reindex 用于换后端或补齐存量。

### 降级语义（红线）

语义是增强不是依赖，以下情况一律优雅降级，关键词检索照常，不报错、不打断命令：

- 索引为空：语义结果为空，静默返回（无告警）；
- 后端不可用或嵌入失败（含 api 配置无效）：语义结果为空，stderr 输出 `warning: semantic search skipped: ...`；
- 索引同步失败只向 stderr 告警，业务写入不回滚。

红线三句：检索不阻塞、增量一致、配置驱动且默认离线。

### 示例（mock 下实跑）

下面示例全部可在未配置 key（mock LLM）时复现，语义走默认 `local` 后端、零外部依赖。先把数据目录指到临时目录（初始化写法见「判断权与分歧」），再建一部作品：

```powershell
$env:NOVEL_DATA_DIR = "$env:TEMP\novel-n7\data"
$env:NOVEL_CONFIG  = "$env:TEMP\novel-n7\config.toml"
Remove-Item Env:NOVEL_LLM_API_KEY, Env:NOVEL_LLM_BASE_URL, Env:NOVEL_LLM_MODEL -ErrorAction SilentlyContinue
```

```bash
uv run novel-editorial works create 语义之书 --genre 悬疑 --description 侦探深夜查案
# created workspace <作品ID>: 语义之书
```

以写手身份写两条意思相近但无共同关键词的笔记（「归乡/回乡」「钟声/钟鸣」「想起/在耳边响起」互为近义写法，两条笔记没有任何共同双字词）：

```bash
uv run novel-editorial memory note <作品ID> 写手 --content 深夜归乡他总想起钟声 --as 写手
# note added to 写手 by 写手

uv run novel-editorial memory note <作品ID> 写手 --content 雨夜回乡的钟鸣在耳边响起 --as 写手
# note added to 写手 by 写手
```

查询词「雨夜归乡的钟声」与两条笔记都没有字面重叠，普通检索查不到：

```bash
uv run novel-editorial memory search <作品ID> 雨夜归乡的钟声
# no matches
```

加 `--semantic` 后按意思联想命中，相似度降序追加在结果末尾：

```bash
uv run novel-editorial memory search <作品ID> 雨夜归乡的钟声 --semantic
# [笔记] 深夜归乡他总想起钟声（来源: 写手）[语义 0.51]
# [笔记] 雨夜回乡的钟鸣在耳边响起（来源: 写手）[语义 0.44]
```

`memory reindex` 重建索引（幂等，重复执行条数不变），重建后语义检索结果不变：

```bash
uv run novel-editorial memory reindex <作品ID>
# reindexed 2 entries

uv run novel-editorial memory reindex <作品ID>
# reindexed 2 entries

uv run novel-editorial memory search <作品ID> 雨夜归乡的钟声 --semantic
# [笔记] 深夜归乡他总想起钟声（来源: 写手）[语义 0.51]
# [笔记] 雨夜回乡的钟鸣在耳边响起（来源: 写手）[语义 0.44]
```

（`<作品ID>` 换成上一步输出的 ID，每次运行不同；`local` 后端是确定性算法，相似度分数每次运行一致，换 `api` 后端后会不同。）

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功 |
| `1` | 业务错误（找不到对象、配置错误、LLM 调用失败等） |
| `2` | 用法错误（参数错误、状态机冲突如重复拍板 / 修订已接受草稿） |
| `3` | 未预期的系统错误 |

## 常见问题（FAQ）

### 不配 key 能跑吗？

能。没有 `NOVEL_LLM_API_KEY` 时程序使用确定性 mock：对话回复固定为「（模拟回复）」，`demo` 也能一条命令跑通完整闭环。语义记忆检索的默认 `local` 后端同样不需要 key，离线可复现（见「语义记忆检索（N7）」）。配了 key 后同样的命令自动换成真实模型，不需要改代码。

### 数据存在哪？怎么换目录？

默认在 `./data`：`global.db` 是作品注册表，每部作品的数据在 `works/<作品ID>/data.db`。想换目录就设置 `NOVEL_DATA_DIR` 再跑命令，首次运行会自动建库（`init` 幂等，可随时重跑）。

### 怎么换 LLM 供应商？

改 `NOVEL_LLM_API_KEY`、`NOVEL_LLM_BASE_URL`、`NOVEL_LLM_MODEL` 三个环境变量，指向任意 OpenAI 兼容的 `/chat/completions` 接口即可，示例见上文「换 LLM 供应商」。语义检索的 `api` 后端复用 `NOVEL_LLM_BASE_URL` / `NOVEL_LLM_API_KEY`，再单独配置 `NOVEL_EMBEDDING_MODEL`（见「语义记忆检索（N7）」）。

### 质量门怎么调？quality_failed 是什么意思？

阈值默认 8，越小越严格，通过条件与得分公式见上文「质量门」。`quality_failed` 表示最近一次生成或修订没过门：此时不能 `decision accept`，可以 `decision reject` 退掉，或修改风格、调整内容后 `draft revise` 重跑。

### demo 和真实写作有什么区别？

`demo` 是单命令、确定性的端到端演示：自动创建《演示之书》，走「对话 → 生成草稿 → 质量门 → 拍板」，mock 下回复固定，且不设置风格锚点。真实写作是 README 快速开始里的逐条命令，由你自己按节奏推进、给意见、拍板。

### 多部作品会串吗？

不会。每部作品一个独立 SQLite 文件，数据按 `<作品ID>` 隔离，有专门的多作品隔离测试保障。

### 私有记忆的权限规则是什么？

作者只读；伙伴只能以自己的身份写自己的笔记；`--as` 只做权限校验、不落库。多写手下目标按名字定位、`--as` 按角色校验（`--as 写手` 可以写给任一位写手实例）。完整规则与示例见上文「私有记忆的权限规则」与「多写手并行（N14）」。

### 怎么查看编辑部当前状态？

- `agents list <作品ID>`：按创建顺序列出班底（角色 + 名字 + ID，见「多写手并行（N14）」）；
- `agents show <作品ID>`：完整档案与当前情绪；
- `works show <作品ID>`：班子一览（含作品状态行与结构树，见「作品结构与创作进度（N13）」）；
- `memory view <作品ID> --as 作者`：老板视图（档案、班子状态、草稿、最近意见与决策）；
- `log <作品ID>`：全流程回顾（对话 / 状态 / 草稿 / 意见 / 决策）；
- `talk list <作品ID>`：对话记录；
- `events list <作品ID>` / `inspect <作品ID> <关键词>` / `decision pending <作品ID>`：事件流、穿透查询与待拍板提醒（见「可见性」）。

### 我配了 .env 为什么不生效？

程序不会自动读取 `.env` 文件。把 `.env` 里的变量用 `export`（bash）或 `$env:`（PowerShell）读入当前会话，或按上文「.env 的用法」由 shell 加载。

### 怎么备份？仓库根目录那个 zip 是什么？

备份 = 复制 `NOVEL_DATA_DIR` 整个目录，恢复时放回原位。仓库根目录的 `novel-editorial-backup-*.zip` 只是仓库备份用途，不是运行时数据的备份机制。

### 命令报错时那个数字是什么意思？

是退出码：`0` 成功、`1` 业务错误、`2` 用法错误、`3` 未预期错误，见上文「退出码」。

### 支持哪些 Python 版本？Windows 能用吗？

Python 3.11 或 3.12（项目约束 `>=3.11,<3.13`），uv 会自动按 `.python-version` 取解释器。Windows、macOS、Linux 都能用，本文档给出了 PowerShell 与 bash 两种写法。
