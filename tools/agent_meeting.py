"""Multi-agent weekly meeting engine.

Flow: write weekly diaries -> chair picks attendees -> 3 rounds of discussion
-> chair summary report -> archive to weekly_meetings and apply decisions.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from novel_pipeline.llm_client import chat_deepseek, estimate_cost  # noqa: E402
from novel_pipeline.services import activity  # noqa: E402
from novel_pipeline.services import knowledge  # noqa: E402
from tools import architect_weekly, write_diaries  # noqa: E402

AGENTS_DIR = ROOT / "prompts" / "agents"
CORE_AGENTS = ["planner", "guard", "writer", "reader", "memory", "eic"]
ALL_AGENTS = CORE_AGENTS + [
    "editor", "reviewer", "work_meta", "ending_judge", "knowledge_keeper",
]


def parse_json(text):
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text) or re.search(r"\{[\s\S]*$", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        t = m.group(0)
        import re as _re
        clean = _re.sub(r",\s*([}\]])", "\\1", t)
        for _ in range(8):
            m1 = _re.search(r',\s*"[^"]*"?\s*:\s*"[^"]*$', clean)
            if m1:
                clean = clean[: m1.start()]
                continue
            m2 = _re.search(r',\s*"[^"]*"$', clean)
            if m2:
                clean = clean[: m2.start()]
                continue
            break
        stack = []
        in_str = False
        esc = False
        for ch in clean:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
                continue
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]" and stack:
                stack.pop()
        while stack:
            clean += "}" if stack.pop() == "{" else "]"
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            return None


def agent_md(agent):
    p = AGENTS_DIR / f"{agent}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def agent_model(agent):
    """Resolve the model from the agent frontmatter (default flash)."""
    p = AGENTS_DIR / f"{agent}.md"
    if p.exists():
        text = p.read_text(encoding="utf-8")
        if text.startswith("---"):
            head = text.split("---", 2)[1]
            for line in head.strip().splitlines():
                if line.strip().startswith("model:"):
                    return line.split(":", 1)[1].strip() or "deepseek-v4-flash"
    return "deepseek-v4-flash"


def record_cost(conn, novel_id, agent, usage, model):
    cost = estimate_cost(model, usage)
    conn.execute(
        "INSERT INTO cost_logs(novel_id,node_name,model,prompt_tokens,completion_tokens,cost,created_at) "
        "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
        (
            novel_id,
            "会议:" + agent,
            model,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
            cost,
        ),
    )
    conn.commit()


def latest_weekly(conn, novel_id, agent):
    row = conn.execute(
        "SELECT content FROM agent_diaries WHERE agent=? AND novel_id=? "
        "AND diary_type='weekly' ORDER BY id DESC LIMIT 1",
        (agent, novel_id),
    ).fetchone()
    return json.loads(row["content"]) if row and row["content"] else None


def mood_of(conn, novel_id, agent):
    row = conn.execute(
        "SELECT mood FROM agent_states WHERE agent=? AND novel_id=? ORDER BY id DESC LIMIT 1",
        (agent, novel_id),
    ).fetchall()
    return json.loads(row[0]["mood"]) if row and row[0]["mood"] else None


GET_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_knowledge",
        "description": (
            "获取与当前议题相关的写作知识包。当讨论涉及开篇/钩子、节奏/爽点、"
            "人设/OOC、伏笔、去AI味、市场热点/选题等主题时，调用本工具获取内容后再发言。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "知识主题关键词，例如：章末钩子、节奏、OOC、伏笔、去AI味、市场热点",
                }
            },
            "required": ["topic"],
        },
    },
}

GET_NOVEL_KNOWLEDGE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_novel_knowledge",
        "description": (
            "获取当前这部小说的设定知识库：角色当前状态、世界观规则、物品/金手指、"
            "势力、地点、力量体系、剧情事实与时间线。讨论设定一致性时必须调用本工具确认，"
            "禁止凭记忆编造或遗忘已有设定。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "查询关键词，例如：角色名、物品名、境界、地点、势力、事件",
                }
            },
            "required": ["topic"],
        },
    },
}


def ask(conn, novel_id, agent, user, temperature, dry_run, mock_text, max_tokens=3000,
        tools=None, messages=None, system_override=None):
    if dry_run:
        return mock_text, {"prompt_tokens": 0, "completion_tokens": 0}, "dry-run", []
    system = system_override if system_override is not None else agent_md(agent)
    model = agent_model(agent)
    first = chat_deepseek(
        model, system, user, temperature=temperature,
        max_tokens=max_tokens, messages=messages, tools=tools,
    )
    tool_calls = first.get("tool_calls") or []
    usage = dict(first.get("usage") or {})
    if not tool_calls:
        record_cost(conn, novel_id, agent, usage, first["model"])
        return first["text"], usage, first["model"], []
    # Tool loop: resolve local knowledge, then one final no-tools round.
    msgs = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": first.get("text") or "", "tool_calls": tool_calls},
    ]
    from novel_pipeline.services import knowledge  # noqa: PLC0415

    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        topic = str(args.get("topic") or "")
        if name == "get_knowledge":
            hits = knowledge.resolve_knowledge(agent, topic)
            content = "\n\n".join(
                f"【{h['title']}】\n{h['content']}" for h in hits
            ) or f"未找到与「{topic}」匹配的知识包，请直接作答。"
        elif name == "get_novel_knowledge":
            from tools import novel_knowledge  # noqa: PLC0415

            hits = novel_knowledge.resolve(conn, novel_id or 0, topic)
            content = "\n\n".join(
                f"【{h['category']}·{h['entity']} v{h['version']}】\n{h['content']}"
                for h in hits
            ) or f"知识库中没有与「{topic}」相关的设定，请基于已有材料作答。"
        else:
            content = "未知工具"
        msgs.append(
            {"role": "tool", "tool_call_id": tc.get("id") or "", "content": content}
        )
    final = chat_deepseek(
        model, None, None, temperature=temperature, max_tokens=max_tokens, messages=msgs
    )
    final_usage = final.get("usage") or {}
    usage = {
        "prompt_tokens": int(usage.get("prompt_tokens") or 0)
        + int(final_usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0)
        + int(final_usage.get("completion_tokens") or 0),
    }
    record_cost(conn, novel_id, agent, usage, final["model"])
    return final["text"], usage, final["model"], []


def build_materials_dict(conn, novel_id):
    m = architect_weekly.build_materials(conn, novel_id)
    if m is None:
        raise RuntimeError("no novel found")
    return m


def compress_history(conn, novel_id, new_speeches, prev_summary="", dry_run=False):
    """Incrementally compress meeting history with the memory agent.

    Each round compresses only the speeches added since the last compression,
    merging them into the previous summary. Keeps global context without
    blowing up the per-attendee prompt (long raw histories pushed some
    models into empty-content loops).
    """
    if not new_speeches:
        return {"summary": prev_summary}
    user = (
        "你是会议记录员。请把以下新增发言合并进已有的会议进展摘要，只输出 JSON："
        "{summary(200-350字，覆盖已提出的方向/观点/分歧/共识/待决问题), "
        "positions(对象：角色名->一句话立场), open_questions(数组), agreements(数组)}。"
        "要求：保留每位参会者的核心观点与分歧，不遗漏新信息，语言精炼、像人话。"
        "已有摘要：" + (prev_summary or "无")
        + "；新增发言：" + json.dumps(new_speeches, ensure_ascii=False)
    )
    text, _usage, _model, _tc = ask(
        conn, novel_id, "memory", user, temperature=0.3, dry_run=dry_run,
        mock_text=json.dumps(
            {"summary": "[dry-run] 会议进展摘要", "positions": {},
             "open_questions": [], "agreements": []},
            ensure_ascii=False,
        ),
        max_tokens=1200,
    )
    parsed = parse_json(text) or {"summary": text[:1000]}
    return {"summary": json.dumps(parsed, ensure_ascii=False)}


def chair_pick(conn, novel_id, dry_run, materials, topic=""):
    ctx = materials["context"]
    planning = bool(ctx.get("new_book_planning"))
    finish_metrics = {
        "published": ctx.get("published_chapters", 0),
        "target": ctx.get("target_chapters", 0),
        "open_plot_threads": len(ctx.get("open_plot_threads") or []),
        "last_chapter_seq": ctx.get("last_chapter_seq", 0),
    }
    meeting_note = (
        "当前还没有作品，这是一次新书选题会：讨论写什么书、题材与卖点、读者定位、开篇钩子、"
        "主角与世界观方向。参会名单应包含 planner、reader、memory、guard、writer、eic 等策划向成员。"
        if planning
        else ""
    )
    user = (
        "你是会议主席，请根据会议材料与各位 Agent 的本周心情，决定本次参会名单（最多 8 人，必须包含你自己 eic）"
        "与讨论议题。只输出JSON：{attendees(数组, 从这些名字中选: planner,guard,writer,editor,reviewer,reader,memory,work_meta,ending_judge), topics(数组, 2-4个议题)}。"
        + (f"本次是专题会议，用户指定的主题为「{topic}」，topics 必须以它为核心展开（可补充相关子议题）。" if topic else "")
        + meeting_note
        + f"完结指标：{json.dumps(finish_metrics, ensure_ascii=False)}；"
        "规则：若已发布章数达到目标章数的 80% 以上（目标>0），或活跃伏笔回收过半、剧情明显进入终局，参会名单必须包含 ending_judge。"
        "会议材料：" + json.dumps(materials["context"], ensure_ascii=False)
        + "；全员心情：" + json.dumps(
            {a: mood_of(conn, novel_id, a) for a in ALL_AGENTS}, ensure_ascii=False
        )
    )
    text, _, _, _ = ask(
        conn, novel_id, "eic", user, temperature=0.2, dry_run=dry_run,
        mock_text=json.dumps(
            {"attendees": ["planner", "memory", "reader", "guard", "writer", "eic"],
             "topics": ["下一周主线", "伏笔回收", "完读率观察"]}
        ),
    )
    parsed = parse_json(text) or {}
    attendees = parsed.get("attendees") or CORE_AGENTS
    attendees = [a for a in attendees if a in ALL_AGENTS or a == "eic"]
    if "eic" not in attendees:
        attendees.insert(0, "eic")
    attendees = attendees[:8]
    return attendees, parsed.get("topics") or ["下一周规划"], parsed


def round_speech(conn, novel_id, agent, materials, history, round_no, dry_run,
                 instruction="", topic="", compressed_history=""):
    weekly = latest_weekly(conn, novel_id, agent)
    mood = mood_of(conn, novel_id, agent)
    brief = materials["agent_briefs"].get(agent, {})
    planning = bool((materials.get("context") or {}).get("new_book_planning"))
    user = (
        f"现在是会议第 {round_no} 轮。"
        + (f"本次会议主题：{topic}。" if topic else "这是周会。")
        + (
            "当前没有作品，这是新书选题会：请围绕题材选择、市场热点、读者定位、主角与世界观、"
            "书名与开篇钩子、连载可行性发表意见，并给出可落地的提案。"
            if planning
            else ""
        )
        + (f"用户指示：{instruction}。请优先响应并落实到你的发言中。" if instruction else "")
        + ("请先回应其他参会者的发言，再发表你的意见。" if round_no > 1 else "请基于你的周记先做本周小结，再发表意见。")
        + "我的本周简报：" + json.dumps(brief, ensure_ascii=False)
        + "；我的本周日记：" + json.dumps(weekly or {}, ensure_ascii=False)
        + "；我的心情：" + json.dumps(mood or {}, ensure_ascii=False)
        + "；会议材料摘要：" + json.dumps({k: materials["context"][k] for k in (
            "book_name", "volume_goal", "published_chapters", "stock_chapters",
            "quality_summary", "reader_stats", "open_plot_threads", "last_chapter_seq",
        )}, ensure_ascii=False)
        + (
            "；历史发言摘要：" + compressed_history
            if compressed_history
            else "；历史发言（共 " + str(len(history)) + " 条，展示最近 2 条）："
            + json.dumps(history[-2:], ensure_ascii=False)
        )
        + (
            "；最近发言：" + json.dumps(history[-2:], ensure_ascii=False)
            if compressed_history
            else ""
        )
    )
    natural_rule = (
        "发言要像一个真实的人在群里说话：先输出 speech 字段——第一人称、自然口语、"
        "带自己的性格和情绪（可以有小停顿、口头禅、语气词），像在群里打字聊天，"
        "150-300 字，不要分点列举、不要用「首先/其次/最后」、不要 AI 腔总结。"
        "再输出结构化字段供会议记录使用。"
    )
    json_rule = (
        "严格只输出一个 JSON 对象，字段为：speech(字符串,自然发言全文), weekly_summary(字符串), feelings(字符串), "
        "opinion(字符串), concerns(字符串数组), proposals(字符串数组), priority(字符串)。"
        "不要输出 JSON 以外的任何文字、Markdown、注释或解释。"
    )
    mock_text = json.dumps(
        {"speech": f"[dry-run] {agent} 的发言", "weekly_summary": f"[dry-run] {agent} 本周小结",
         "feelings": "平稳", "opinion": "建议保持节奏", "concerns": [],
         "proposals": ["观察下一周数据"], "priority": "中"},
        ensure_ascii=False,
    )
    index = knowledge.build_knowledge_index(agent)
    tool_rule = (
        "\n\n[可用工具]\n"
        "1. get_knowledge：通用写作知识包（开篇/钩子、节奏/爽点、人设/OOC、伏笔、"
        "去AI味、市场热点/选题），涉及这些主题时调用。\n"
        "2. get_novel_knowledge：当前小说的设定知识库（角色状态/世界观/物品/势力/"
        "地点/力量体系/剧情事实/时间线），讨论设定一致性时调用。\n"
        "按需自主调用，可多次调用；调用后基于返回内容按[会议模式]输出最终 JSON。"
    )
    system = agent_md(agent) + tool_rule + ("\n\n" + index if index else "")
    user += "；" + natural_rule + "；" + json_rule

    text, _usage, _model, tool_calls = ask(
        conn, novel_id, agent, user, temperature=0.6, dry_run=dry_run,
        mock_text=mock_text,
        tools=[GET_KNOWLEDGE_TOOL, GET_NOVEL_KNOWLEDGE_TOOL],
        system_override=system,
    )
    if tool_calls:
        tools_used = []
        for tc in tool_calls:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            tools_used.append(
                f"{fn.get('name') or 'unknown'}({str(args.get('topic') or '')})"
            )
        first = parse_json(text)
        if first is None:
            first = {}
        first["_tools_used"] = tools_used
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": text or "", "tool_calls": tool_calls},
        ]
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            tool_topic = str(args.get("topic") or "")
            if name == "get_novel_knowledge":
                from tools import novel_knowledge  # noqa: PLC0415

                hits = novel_knowledge.resolve(conn, novel_id, tool_topic)
                content = "\n\n".join(
                    f"【{h['category']}·{h['entity']} v{h['version']}】\n{h['content']}"
                    for h in hits
                ) or f"知识库中没有与「{tool_topic}」相关的设定，请基于已有材料发言并不要编造新设定。"
            else:
                hits = knowledge.resolve_knowledge(agent, tool_topic)
                content = "\n\n".join(
                    f"【{h['title']}】\n{h['content']}" for h in hits
                ) or f"未找到与「{tool_topic}」匹配的知识包，请直接发言。"
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or "",
                    "content": content,
                }
            )
        text, _usage, _model, _tc2 = ask(
            conn, novel_id, agent, None, temperature=0.6, dry_run=dry_run,
            mock_text=mock_text, messages=msgs, system_override=system,
        )
        result = parse_json(text) or {"raw": text[:2000]}
        if isinstance(result, dict):
            result["_tools_used"] = tools_used
        return result

    parsed = parse_json(text)
    if parsed:
        return parsed
    text, _usage, _model, _tc3 = ask(
        conn, novel_id, agent,
        user + "；你上一次输出不是合法 JSON，请重新严格只输出 JSON 对象，不要任何多余内容。",
        temperature=0.6, dry_run=dry_run, mock_text=mock_text, system_override=system,
    )
    return parse_json(text) or {"raw": text[:2000]}


def chair_summary(conn, novel_id, attendees, topics, transcript, dry_run, materials):
    planning = bool((materials.get("context") or {}).get("new_book_planning"))
    decision_note = (
        "本次是新书选题会：decisions.next_book 必须输出完整的选题提案"
        "（book_name, genre, abstract, selling_point, protagonist, 可加 opening_hook 与 target_readers）。"
        if planning
        else ""
    )
    user = (
        "你是会议主席，请总结本次周会并输出报告。参会者：" + json.dumps(attendees, ensure_ascii=False)
        + "；议题：" + json.dumps(topics, ensure_ascii=False)
        + "；全部发言：" + json.dumps(transcript, ensure_ascii=False)
        + "。报告格式：{meeting_id, date, attendees, topics, discussion_summary, "
        "cover_prompt(字符串，封面AI绘画提示词，讨论到新书选题或视觉/封面方向时输出，"
        "需包含画面主体、风格流派、色调氛围、构图、文字排版要求，可直接用于豆包等文生图，否则为空字符串), "
        "decisions{blueprint_updates(数组,每项含seq/title/outline/hook_type/hook/emotion), "
        "volume_goal_adjust(字符串,可空), reader_persona({age_range,preference,avoid},可空), "
        "finish_decision({should_finish(bool), remaining_chapters(5-30,不收尾则为0), reasons(数组)},可空), "
        "next_book({book_name, genre, abstract, selling_point, protagonist},仅当作品已完结时输出)}, "
        "disagreements(数组), action_items(数组)}"
        + decision_note
    )
    text, _, _, _ = ask(
        conn, novel_id, "eic", user, temperature=0.2, dry_run=dry_run,
        mock_text=json.dumps(
            {"meeting_id": "dry-run", "date": datetime.now().strftime("%Y-%m-%d"),
             "attendees": attendees, "topics": topics,
             "discussion_summary": "dry-run 会议", "decisions": {"blueprint_updates": [], "volume_goal_adjust": ""},
             "cover_prompt": "",
             "disagreements": [], "action_items": []}
        ),
        max_tokens=4000,
    )
    return parse_json(text) or {"raw": text[:2000]}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="多 Agent 周会会议引擎")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--novel-id", type=int, default=0)
    ap.add_argument("--book-id", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--topic", default="")
    ap.add_argument("--kind", choices=["weekly", "topic"], default="weekly")
    ap.add_argument("--out", default="", help="override archive dir for the meeting JSON")
    args = ap.parse_args()

    topic = args.topic
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        novel_id = args.novel_id
        if not novel_id and args.book_id:
            r = conn.execute(
                "SELECT id FROM novels WHERE book_id=? ORDER BY id DESC LIMIT 1",
                (args.book_id,),
            ).fetchone()
            novel_id = r["id"] if r else 0
        if not novel_id:
            r = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
            novel_id = r["id"] if r else 0
        if not novel_id:
            print(json.dumps({"ok": False, "error": "no novel"}, ensure_ascii=False))
            return
        materials = build_materials_dict(conn, novel_id)
        if args.kind == "weekly":
            write_diaries.write(
                conn, novel_id, "weekly", dry_run=args.dry_run, materials=materials
            )
        attendees, topics, pick = chair_pick(
            conn, novel_id, args.dry_run, materials, topic
        )
        if topic:
            topics = [topic] + [t for t in (topics or []) if t != topic]
        transcript = []
        for round_no in range(1, args.rounds + 1):
            for agent in attendees:
                speech = round_speech(
                    conn, novel_id, agent, materials, transcript, round_no,
                    args.dry_run, topic=topic,
                )
                transcript.append({"round": round_no, "agent": agent, "speech": speech})
                activity.log_activity(
                    conn,
                    agent,
                    novel_id,
                    "meeting_speech",
                    f"会议第 {round_no} 轮发言",
                    {
                        "round": round_no,
                        "kind": args.kind,
                        "speech": str(speech.get("speech") or "")[:500],
                        "proposals": speech.get("proposals") or [],
                    },
                )
        report = chair_summary(
            conn, novel_id, attendees, topics, transcript, args.dry_run, materials
        )
        report["attendees"] = attendees
        report["topics"] = topics
        report["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report.setdefault("decisions", {"blueprint_updates": [], "volume_goal_adjust": ""})
        report.setdefault("disagreements", [])
        report.setdefault("action_items", [])
        report.setdefault("discussion_summary", "")
        report["kind"] = args.kind

        # archive
        cur = conn.execute(
            "INSERT INTO weekly_meetings(held_at,novel_id,attendees,topics,report,status,kind,session_id) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                report["date"],
                novel_id,
                json.dumps(attendees, ensure_ascii=False),
                json.dumps(topics, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                "completed",
                args.kind,
                0,
            ),
        )
        conn.commit()
        weekly_id = cur.lastrowid
        activity.log_activity(
            conn,
            "eic",
            novel_id,
            "meeting_summary",
            "主席总结会议",
            {
                "meeting_id": weekly_id,
                "kind": args.kind,
                "summary": str(report.get("discussion_summary") or "")[:400],
                "action_items": len(report.get("action_items") or []),
            },
        )
        try:
            action_result = activity.generate_post_meeting_actions(
                conn,
                0,
                weekly_id,
                novel_id,
                attendees,
                report,
                transcript,
                dry_run=args.dry_run,
            )
            print(
                json.dumps(
                    {"ok": True, "post_meeting_actions": action_result.get("created", 0)},
                    ensure_ascii=False,
                )
            )
        except Exception as exc:  # noqa: BLE001
            print(f"note: post-meeting actions skipped: {exc}", file=sys.stderr)
            conn.commit()

        # topic meetings write a meeting memory per attendee
        if args.kind == "topic":
            for agent in attendees:
                speech = next(
                    (s["speech"] for s in transcript if s["agent"] == agent),
                    {},
                )
                memory = {
                    "topic": topic,
                    "my_speech": speech,
                    "conclusions": report.get("action_items", []),
                    "date": report["date"],
                }
                conn.execute(
                    "INSERT INTO agent_diaries(agent,novel_id,diary_type,content,created_at) "
                    "VALUES(?,?,?,?,datetime('now','localtime'))",
                    (agent, novel_id, "meeting", json.dumps(memory, ensure_ascii=False)),
                )
            conn.commit()

        # persist decisions
        try:
            from tools.apply_architect import apply_report  # noqa: PLC0415

            apply_report(conn, novel_id, report)
        except (ImportError, AttributeError):
            print("note: apply_report not available yet", file=sys.stderr)

        out = Path(args.out) if args.out else ROOT / "n8n_tmp"
        if out.is_dir():
            out = out / f"meeting_{datetime.now():%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"materials": materials, "pick": pick, "transcript": transcript, "report": report},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "attendees": attendees,
                    "topics": topics,
                    "kind": args.kind,
                    "rounds": args.rounds,
                    "transcript_len": len(transcript),
                    "archive": str(out),
                },
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
