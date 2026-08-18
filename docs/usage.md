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
```

- `quality_threshold`：质量门阈值（整数），默认 `8`；草稿得分 ≤ 阈值才算通过。
- `proactive_enabled`：主动行为总开关（布尔），默认 `true`；`false` 时伙伴的主动发言停发（talk 首轮的责编确认提问除外，见「主动行为」）。
- `proactive_max_per_agent`：每位伙伴在一部作品里的主动发言上限（整数），默认 `3`；达到上限后不再新增，设 `0` 等于不发（talk 首轮提问除外）。
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

阈值优先级：`NOVEL_QUALITY_THRESHOLD` > `config.toml [defaults].quality_threshold` > 内置默认 `8`。

仓库里的 `.env.example` 模板列了 `NOVEL_LLM_API_KEY`、`NOVEL_LLM_BASE_URL`、`NOVEL_LLM_MODEL`、`NOVEL_DATA_DIR`、`NOVEL_LOG_LEVEL`；本表另外补充的 `NOVEL_CONFIG`、`NOVEL_QUALITY_THRESHOLD`、`NOVEL_PROACTIVE_ENABLED` 与 `NOVEL_PROACTIVE_MAX_PER_AGENT` 同样受支持。

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
