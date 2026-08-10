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
from novel_pipeline.llm_client import chat_deepseek  # noqa: E402
from tools import architect_weekly, write_diaries  # noqa: E402

AGENTS_DIR = ROOT / "prompts" / "agents"
CORE_AGENTS = ["planner", "guard", "writer", "reader", "memory", "eic"]
ALL_AGENTS = CORE_AGENTS + ["editor", "reviewer", "work_meta", "ending_judge"]
materials = {"context": {}, "agent_briefs": {}}
topic = ""


def parse_json(text):
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def agent_md(agent):
    p = AGENTS_DIR / f"{agent}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def record_cost(conn, novel_id, agent, usage, model):
    conn.execute(
        "INSERT INTO cost_logs(novel_id,node_name,model,prompt_tokens,completion_tokens,cost,created_at) "
        "VALUES(?,?,?,?,?,0,datetime('now','localtime'))",
        (
            novel_id,
            "会议:" + agent,
            model,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
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


def ask(conn, novel_id, agent, user, temperature, dry_run, mock_text, max_tokens=1600):
    if dry_run:
        return mock_text, {"prompt_tokens": 0, "completion_tokens": 0}, "dry-run"
    resp = chat_deepseek("deepseek-v4-flash", agent_md(agent), user, temperature=temperature, max_tokens=max_tokens)
    record_cost(conn, novel_id, agent, resp["usage"], resp["model"])
    return resp["text"], resp["usage"], resp["model"]


def build_materials_dict(conn, novel_id):
    m = architect_weekly.build_materials(conn, novel_id)
    if m is None:
        raise RuntimeError("no novel found")
    return m


def write_weekly_diaries(conn, novel_id, dry_run):
    for agent in ALL_AGENTS:
        brief = materials["agent_briefs"].get(agent, {})
        user = (
            "写本周日记，回顾这周我干了什么、关键事件、学到的东西、看法变化、心情变化，"
            "并额外输出 mood 字段 {satisfaction(0-1), concern(0-1), excitement(0-1), fatigue(0-1), note}。"
            "我的本周简报：" + json.dumps(brief, ensure_ascii=False)
            + "；我的本周日记与上周周记：" + json.dumps(
                write_diaries.weekly_payload(conn, novel_id, agent), ensure_ascii=False
            )
        )
        text, usage, model = ask(
            conn, novel_id, agent, user,
            temperature=0.6, dry_run=dry_run,
            mock_text=json.dumps(
                {"week_summary": f"[dry-run] {agent} 本周小结", "key_events": [], "learnings": [],
                 "opinions_changed": [], "mood_trend": "平稳", "next_week_focus": "观察",
                 "mood": {"satisfaction": 0.5, "concern": 0.5, "excitement": 0.5, "fatigue": 0.3, "note": ""}}
            ),
        )
        content = parse_json(text) or {"raw": text[:2000]}
        conn.execute(
            "INSERT INTO agent_diaries(agent,novel_id,diary_type,content,created_at) "
            "VALUES(?,?,?,?,datetime('now','localtime'))",
            (agent, novel_id, "weekly", json.dumps(content, ensure_ascii=False)),
        )
        mood = content.get("mood") if isinstance(content, dict) else None
        if not isinstance(mood, dict):
            mood = {"satisfaction": 0.5, "concern": 0.5, "excitement": 0.5, "fatigue": 0.3, "note": ""}
        conn.execute("DELETE FROM agent_states WHERE agent=? AND novel_id=?", (agent, novel_id))
        conn.execute(
            "INSERT INTO agent_states(agent,novel_id,mood,updated_at) VALUES(?,?,?,datetime('now','localtime'))",
            (agent, novel_id, json.dumps(mood, ensure_ascii=False)),
        )
        conn.commit()


def chair_pick(conn, novel_id, dry_run):
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
    text, _, _ = ask(
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


def round_speech(conn, novel_id, agent, materials, history, round_no, dry_run, instruction=""):
    weekly = latest_weekly(conn, novel_id, agent)
    mood = mood_of(conn, novel_id, agent)
    brief = materials["agent_briefs"].get(agent, {})
    planning = bool((materials.get("context") or {}).get("new_book_planning"))
    base = (
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
        + "；历史发言：" + json.dumps(history, ensure_ascii=False)
    )
    json_rule = (
        "严格只输出一个 JSON 对象，字段为：weekly_summary(字符串), feelings(字符串), "
        "opinion(字符串), concerns(字符串数组), proposals(字符串数组), priority(字符串)。"
        "不要输出 JSON 以外的任何文字、Markdown、注释或解释。"
    )
    mock_text = json.dumps(
        {"weekly_summary": f"[dry-run] {agent} 本周小结", "feelings": "平稳",
         "opinion": "建议保持节奏", "concerns": [], "proposals": ["观察下一周数据"],
         "priority": "中"},
        ensure_ascii=False,
    )
    last_text = ""
    for attempt in range(2):
        extra = json_rule if attempt == 0 else (
            json_rule + "你上一次输出不是合法 JSON，请重新严格只输出 JSON 对象，不要任何多余内容。"
        )
        text, _, _ = ask(
            conn, novel_id, agent, base + "；" + extra,
            temperature=0.6, dry_run=dry_run, mock_text=mock_text,
        )
        last_text = text
        parsed = parse_json(text)
        if parsed:
            return parsed
    return {"raw": last_text[:2000]}


def chair_summary(conn, novel_id, attendees, topics, transcript, dry_run):
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
        "decisions{blueprint_updates(数组,每项含seq/title/outline/hook_type/hook/emotion), "
        "volume_goal_adjust(字符串,可空), reader_persona({age_range,preference,avoid},可空), "
        "finish_decision({should_finish(bool), remaining_chapters(5-30,不收尾则为0), reasons(数组)},可空), "
        "next_book({book_name, genre, abstract, selling_point, protagonist},仅当作品已完结时输出)}, "
        "disagreements(数组), action_items(数组)}"
        + decision_note
    )
    text, _, _ = ask(
        conn, novel_id, "eic", user, temperature=0.2, dry_run=dry_run,
        mock_text=json.dumps(
            {"meeting_id": "dry-run", "date": datetime.now().strftime("%Y-%m-%d"),
             "attendees": attendees, "topics": topics,
             "discussion_summary": "dry-run 会议", "decisions": {"blueprint_updates": [], "volume_goal_adjust": ""},
             "disagreements": [], "action_items": []}
        ),
        max_tokens=2400,
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
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--topic", default="")
    ap.add_argument("--kind", choices=["weekly", "topic"], default="weekly")
    args = ap.parse_args()

    global materials, topic
    topic = args.topic
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        novel_id = args.novel_id
        if not novel_id:
            r = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
            novel_id = r["id"] if r else 0
        if not novel_id:
            print(json.dumps({"ok": False, "error": "no novel"}, ensure_ascii=False))
            return
        materials = build_materials_dict(conn, novel_id)
        if args.kind == "weekly":
            write_weekly_diaries(conn, novel_id, args.dry_run)
        attendees, topics, pick = chair_pick(conn, novel_id, args.dry_run)
        if topic:
            topics = [topic] + [t for t in (topics or []) if t != topic]
        transcript = []
        for round_no in range(1, args.rounds + 1):
            for agent in attendees:
                speech = round_speech(
                    conn, novel_id, agent, materials, transcript, round_no, args.dry_run
                )
                transcript.append({"round": round_no, "agent": agent, "speech": speech})
        report = chair_summary(conn, novel_id, attendees, topics, transcript, args.dry_run)
        report["attendees"] = attendees
        report["topics"] = topics
        report["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report.setdefault("decisions", {"blueprint_updates": [], "volume_goal_adjust": ""})
        report.setdefault("disagreements", [])
        report.setdefault("action_items", [])
        report.setdefault("discussion_summary", "")
        report["kind"] = args.kind

        # archive
        conn.execute(
            "INSERT INTO weekly_meetings(held_at,novel_id,attendees,topics,report,status,kind) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                report["date"],
                novel_id,
                json.dumps(attendees, ensure_ascii=False),
                json.dumps(topics, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
                "completed",
                args.kind,
            ),
        )
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

        out = ROOT / "n8n_tmp" / f"meeting_{datetime.now():%Y%m%d_%H%M%S}.json"
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
