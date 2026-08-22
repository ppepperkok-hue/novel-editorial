# M5 实施真元文档（产品形态与开源 · N26 预设编辑部模板）

## 总览

- **大阶段**：M8 产品形态与开源扩展线（backlog 见 docs/project-plan/06-new-capability-backlog.md；N11 已收口，N26 为最后一项 P2 候选）。
- **N26 一句话**：按题材一键生成预设班子与风格起点——网文、同人、正统小说开箱即写，模板只是起点不是边界。
- **现状**：
  - `works create` 默认班子（总编 / 责编 / 写手 / 审稿）由 `store/db.py` 的 DEFAULT_BAND 常量固定，全员同款；
  - N11 示例编辑部已演示「可体验的班子」，但无按题材的预设选择。
- **验收总门**：验证四连全绿 + smoke_m3 + stress_m3；至少一条端到端「`works templates` 列出模板 → `works create --template 网文` → works show 班子字段与模板一致、风格锚点已按模板落好 → 不带 --template 的创建行为与现状逐字节一致」；既有 1135 测试全绿。

## 红线（本阶段强制，06 通用性红线继承）

1. **模板开放**（06 红线 6）：预设模板是起点不是封闭列表；创建后作者随时可用 `agents edit` / `style set` 自定义，模板数量不构成系统能力边界。
2. **不强制**：`--template` 可缺省（缺省 = 默认班子与现状一致）；模板不改变任何创作流程、不设强制关卡、不绑定作品体裁字段。
3. **确定性**：模板是代码常量，相同输入产出相同班子与风格起点；`works templates` 输出稳定有序。
4. **兼容**：不带 `--template` 时 `works create` 行为与现状完全一致（默认班子、无风格锚点）。
5. **体裁自适应**：模板可按题材命名，但任何作品（短篇 / 长篇 / 同人 / 网文 / 诗集）都可套用任意模板。

## 地基影响评估（先评估再动工）

- 无表结构变更、无配置新增、无事件契约变更、无新依赖。
- 新增 `core/templates.py`（模板常量与查询）+ `store/db.py` 班子种子参数化 + `core/workspace.py` 创建支持模板 + `cli/works.py` 命令扩展 + 测试；依赖方向 cli → core → store 不变。
- 模板创建沿用既有 `Agent` 全字段（与 DEFAULT_BAND 同构）；风格起点复用 `set_style_anchor`（模板风格描述非空时落锚，空则不落）。
- 若实现中发现必须破坏性改表 / 改事件契约 / 改错误码，先停下回报，不硬做。

## 子阶段 S1：模板核心与班子种子

### 做什么

- `core/templates.py`（新模块）：
  - `@dataclass(frozen=True) BandTemplate`：name、description、band（list[dict]，每项与 DEFAULT_BAND 同构：role/name/personality/stance/values/aesthetic/emotion_baseline/mood/work_habits/weaknesses/relationship_presets/private_motive）、style_description（str，可为空）。
  - `TEMPLATES: dict[str, BandTemplate]`：至少三个内置模板（键：`网文`、`同人`、`正统`），每个模板的班子四个角色齐全、风格描述非空：
    - 网文：节奏快、钩子密、更新纪律强；风格描述如「节奏快，钩子密，修饰克制」；
    - 同人：尊重原作人设与考据、CP 与关系线敏感；风格描述如「人设贴原作，细节有考据，情感克制」；
    - 正统：文学性、结构完整、留白克制；风格描述如「句子舒展，修饰克制，结构完整」。
  - `get_template(name) -> BandTemplate`：未知模板 NovelError(USAGE_ERROR)（消息含可用清单）。
  - `list_templates() -> list[BandTemplate]`：按固定顺序（网文 / 同人 / 正统）。
- `store/db.py`：把 `seed_default_band` 泛化为 `seed_band(db, workspace_id, members)`（DEFAULT_BAND 不变，`seed_default_band` 委托调用，行为零变化）。
- `core/workspace.py`：`create_workspace(..., template: BandTemplate | None = None)`——template 为空 → 现状行为；非空 → `seed_band(db, workspace_id, template.band)`，且 `template.style_description` 非空时 `set_style_anchor(description=..., forbidden_words="")`。
- tests（`tests/test_templates.py`）：三个模板字段完整（四角色齐全、每项字段齐全）、list 顺序稳定、get 未知模板 USAGE_ERROR、`create_workspace(template=...)` 班子与锚点落库正确、不带 template 行为与现状一致（默认班子、无锚点行）。

### 做到什么程度

- 模板定义、查询与创建可复现；CLI 不接。

### 验收标准

- 单测覆盖上述全部路径；默认创建零回归。

### 验证方式

pytest + ruff + pyright + 宪法校验。

### 暂不做

- CLI（S2）、文档（S3）、用户自定义模板文件 / 模板导入导出、模板编辑命令。

## 子阶段 S2：CLI 与端到端

### 做什么

- 修复 S1 独立审查两个 P3（允许触碰 core/templates.py 与 tests/test_templates.py）：
  - `list_templates()` 顺序直接从 `TEMPLATES`（字典插入序）推导，删除独立 `_ORDER`，杜绝「新增模板漏更顺序元组导致 KeyError / 列出不全」的漂移风险；
  - `get_template()` 返回 `copy.deepcopy(template)`，冻结契约真实生效——调用方改动返回对象不再污染共享常量，确定性保证成立。
- `cli/works.py`：
  - `works create` 新增 `--template <名称>`（缺省 None）：传给 `create_workspace`；未知模板 → USAGE_ERROR（退出码 2）；输出保持 `created workspace <id>: <title>`；
  - 新增 `works templates`：每行 `<名称>: <描述>`，固定顺序。
- tests：registry 的 works 组补 `templates` 与 create 的 `--template` 帮助；端到端「works templates 列出 → create --template 网文 → show 班子角色字段与模板一致、style show 显示模板风格 → create 不带模板与现状一致 → 未知模板退出码 2」。

### 做到什么程度

- 新作者一条命令选体裁班子，开箱即写；旧命令完全兼容。

### 验收标准

- 端到端用例 + 失败路径；smoke_m3 仍 SMOKE OK；stress_m3 无回归。

### 验证方式

pytest（新增用例）+ smoke_m3 + stress_m3 + ruff + pyright + 宪法。

### 暂不做

- 模板编辑 / 自定义模板文件、模板导入导出、按模板预置结构或大纲。

## 子阶段 S3：文档、全量回归与收口

### 做什么

- usage.md 增「预设编辑部模板（N26）」小节（放在「示例编辑部（N11）」附近）：`works templates` / `works create --template` 用法、三个模板说明、模板开放与自定义路径（agents edit / style set）、mock 实跑示例。
- 全量回归 + 独立审查 + 归档 docs/reviews/（20260822-M5N26S1 / S2 / S3 链）。

### 做到什么程度

- 文档与行为一致、示例可复现；全量 1135+ 测试、smoke_m3、stress_m3 全绿，审查链收敛 Ready。

### 验收标准

- 文档示例实跑生效；审查链收敛，归档 docs/reviews/。

### 验证方式

pytest + ruff + pyright + 宪法 + smoke_m3 + stress_m3 + 文档实跑。

### 暂不做

- 自定义模板文件、模板市场、模板版本管理。

## 变更纪律

- 聊天中临时冒出的想法先回写本文档，才算正式变更。
- 每个子阶段完成即停，回报三问（用户授权低价窗口内自主推进时，由总监按验收门收口后进入下一子阶段）。

## 状态

- 立项（2026-08-22）：实施文档就绪，用户授权低价窗口内自主推进，拆包 S1。
