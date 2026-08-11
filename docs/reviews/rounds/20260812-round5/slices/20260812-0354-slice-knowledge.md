验证完成。我已完成语法编译、定向测试（36 个切片相关测试全部通过）、关键 bug 复现和依赖契约核对。现在给出最终审查报告。

**审查范围**：`prompts/`（agents + knowledge 提示词资产）、`tools/novel_knowledge.py`、`tools/knowledge_keeper.py`、`tools/distill_lessons.py`、`tools/clean_novel_knowledge.py`、`tools/ai_taste_check.py`、`tools/export_agent_prompts.py`；仅核对 `novel_editorial/db.py`、`config.py`、`services/knowledge.py`、`services/audit.py`、`services/activity.py`、`llm_client.py` 的契约。

**基线结果**：`python -m compileall` 全部通过（exit 0）；切片定向测试 `test_novel_knowledge / test_clean_knowledge / test_knowledge_keeper / test_distill_lessons / test_ai_taste_check / test_knowledge / test_knowledge_bible` 共 36 个全部通过（4.38s）。按指示未运行全量测试套件。

**已复现的关键缺陷**：`sync_from_chapters` 对 `character_states` 无类型防御，LLM 输出非空 JSON 数组时 `(states or {}).items()` 抛 `AttributeError: 'list' object has no attribute 'items'`（已用临时库复现）；`distill_lessons._meeting_material` 的 session 分支硬编码 `attendees: []`，丢弃表中已存参会者（已复现：存储 `["writer","editor"]`，material 返回 `[]`）。

```json
{
  "findings": [
    {
      "title": "[P1] sync_from_chapters 对 character_states 缺类型防御，LLM 输出数组即整批同步崩溃",
      "body": "tools/novel_knowledge.py:394-401 中 `states = json.loads(row[\"character_states\"] or \"{}\")` 后直接 `for name, state in (states or {}).items()`，没有像同一函数中 world_events 那样做 `isinstance(ev, dict)` 防御。已复现：当 chapter_summaries.character_states 存 JSON 数组（如 `[{\"name\":\"张三\",\"state\":\"重伤\"}]`）时抛出 `AttributeError: 'list' object has no attribute 'items'`，`sync_from_chapters`/`sync_latest` 整批中断，后续章节全部不处理且无降级。LLM 摘要输出格式不可控，作者在 world_events 处已有防御意图，此处属不对称遗漏。建议在解析后校验 `isinstance(states, dict)`，非 dict 时按 `{}` 处理。",
      "confidence_score": 0.95,
      "priority": 1,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\novel_knowledge.py",
        "line_range": {"start": 394, "end": 401}
      }
    },
    {
      "title": "[P2] distill_lessons 的 session 分支硬编码 attendees/kind，丢弃已存参会者信息",
      "body": "tools/distill_lessons.py:62-67 的 `_meeting_material` session 分支返回 `\"attendees\": []` 且 `\"kind\": \"topic\"` 硬编码，而 meeting_sessions 表存在 attendees 与 kind 字段（agent_meeting.py:619 会写入），weekly 分支（line 95）也正确解析。已复现：库中存储 `[\"writer\",\"editor\"]`，material 返回空列表。结果蒸馏 prompt 中参会者为空，模型无法按参会者分配 lessons 的 agents 字段，蒸馏质量下降。建议改为 `_safe_load_json(d.get(\"attendees\") or \"[]\", [])` 并读取 `d.get(\"kind\") or \"topic\"`。",
      "confidence_score": 0.9,
      "priority": 2,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\distill_lessons.py",
        "line_range": {"start": 62, "end": 67}
      }
    },
    {
      "title": "[P3] clean_novel_knowledge 的 --dry-run 参数从未读取，属死参数",
      "body": "tools/clean_novel_knowledge.py main() 中 `ap.add_argument(\"--dry-run\", action=\"store_true\", default=True)` 定义了参数，但代码只检查 `args.apply`，`args.dry_run` 从不使用。用户传不传 `--dry-run` 行为完全相同（默认即 dry-run，除非 `--apply`），且 `--dry-run --apply` 组合会直接执行写入，与 CLI 直觉相反，容易误导操作者。建议删除该参数或真正读取它并在与 --apply 同传时拒绝执行。",
      "confidence_score": 0.95,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\clean_novel_knowledge.py",
        "line_range": {"start": 292, "end": 296}
      }
    },
    {
      "title": "[P3] clean_novel_knowledge 备份文件名硬编码 demo- 前缀",
      "body": "tools/clean_novel_knowledge.py main() 中备份文件固定命名为 `demo-{stamp}.db`，即使通过 `--db` 指定其他数据库文件（如生产库 novel.db），备份也以 demo 命名，恢复时容易混淆。建议用 `path.stem` 派生备份名前缀。",
      "confidence_score": 0.95,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\clean_novel_knowledge.py",
        "line_range": {"start": 320, "end": 324}
      }
    },
    {
      "title": "[P3] sync_latest 的 DISTINCT+ORDER BY 依赖 SQLite 未定义行为",
      "body": "tools/novel_knowledge.py:562-565 `SELECT DISTINCT c.novel_id ... ORDER BY cs.id DESC LIMIT 1` 中 ORDER BY 列 cs.id 不在结果集中。SQLite 文档（lang_select.html#the_order_by_clause）明确说明 DISTINCT 查询中 ORDER BY 表达式必须出现在结果集，否则可能被忽略。当前环境 SQLite 3.45.1 实测行为正确（200 次随机对照无偏差），但跨版本/跨查询计划升级后可能返回任意 novel_id，导致同步到错误的小说。建议改为子查询 `SELECT novel_id FROM (SELECT c.novel_id FROM chapter_summaries cs JOIN chapters c ON c.id=cs.chapter_id ORDER BY cs.id DESC LIMIT 1)` 或 `GROUP BY` 写法。",
      "confidence_score": 0.7,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\novel_knowledge.py",
        "line_range": {"start": 562, "end": 565}
      }
    },
    {
      "title": "[P3] 冲突草稿按 title 去重，跨小说同名实体漏建草稿",
      "body": "tools/novel_knowledge.py `_add_conflict_draft` 用 `SELECT id FROM knowledge_drafts WHERE kind='knowledge' AND source='auto_conflict' AND title=? AND status='draft'` 判断是否已建草稿，但 knowledge_drafts 表无 novel_id 字段（db.py schema），因此小说 A 已有同名实体草稿时，小说 B 的同名实体冲突不会生成新草稿，多小说场景下冲突提示丢失。若多小说共用知识库，建议草稿查重加入 novel 维度（表加列或 title 前缀区分）。",
      "confidence_score": 0.8,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\novel_knowledge.py",
        "line_range": {"start": 117, "end": 126}
      }
    },
    {
      "title": "[P3] knowledge_keeper/distill_lessons 对 usage 字段无空值防御",
      "body": "tools/knowledge_keeper.py:129-131 与 tools/distill_lessons.py:171-173 直接调用 `resp[\"usage\"].get(\"prompt_tokens\")`，而 `chat_deepseek`（llm_client.py）返回 `data.get(\"usage\", {})`：当 API 响应含 `\"usage\": null` 时返回 None，随后 `.get` 抛 AttributeError 导致维护/蒸馏任务崩溃。DeepSeek 正常响应均含 usage，属低概率路径，但加一行 `(resp[\"usage\"] or {}).get(...)` 即可消除。",
      "confidence_score": 0.6,
      "priority": 3,
      "code_location": {
        "absolute_file_path": "E:\\code\\novel-editorial\\tools\\knowledge_keeper.py",
        "line_range": {"start": 129, "end": 131}
      }
    }
  ],
  "overall_correctness": "patch is incorrect",
  "overall_explanation": "审查切片（prompts + 6 个 tools 文件）语法编译通过，36 个定向测试全部通过，正常输入路径功能完整；但存在一个已复现的 P1 缺陷（sync_from_chapters 对 LLM 输出的 character_states 无类型防御，数组输入即整批崩溃）和一个已复现的 P2 信息丢失（distill session 分支丢弃 attendees），以及 5 个 P3 级问题（死参数、硬编码备份名、跨版本脆弱 SQL、草稿去重缺 novel 维度、usage 空值）。按严格标准 patch 并非完全无 bug，建议优先修复 P1 后合入。",
  "overall_confidence_score": 0.88
}
```
