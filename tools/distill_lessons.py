"""Distill lessons from a meeting into knowledge_drafts.

Reads the meeting transcript/report, this week's agent diaries, quality
reports and reader feedback, then asks a flash model to extract actionable
lessons (what went wrong, what to change next round) and stores them as
draft knowledge cards for human review.

CLI:
    python tools/distill_lessons.py [--meeting-id N] [--session-id N] [--db PATH]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.llm_client import chat_deepseek  # noqa: E402
from novel_pipeline.services import knowledge  # noqa: E402


def _parse_json(text):
    if not text:
        return None
    try:
        return json.loads(text[text.find("{") : text.rfind("}") + 1])
    except (ValueError, IndexError):
        return None


def _meeting_material(conn, meeting_id=None, session_id=None):
    if session_id:
        row = conn.execute(
            "SELECT * FROM meeting_sessions WHERE id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            transcript = json.loads(d.get("transcript") or "[]")
        except ValueError:
            transcript = []
        report = {}
        if d.get("report"):
            try:
                report = json.loads(d["report"])
            except ValueError:
                report = {}
        return {
            "id": d["id"],
            "kind": "topic",
            "topic": d.get("topic", ""),
            "attendees": [],
            "transcript": transcript,
            "report": report,
            "source": f"session:{d['id']}",
        }
    if meeting_id:
        row = conn.execute(
            "SELECT * FROM weekly_meetings WHERE id=? ORDER BY id DESC LIMIT 1",
            (meeting_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM weekly_meetings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        report = json.loads(d.get("report") or "{}")
    except ValueError:
        report = {}
    return {
        "id": d["id"],
        "kind": d.get("kind") or "weekly",
        "topic": "、".join(
            json.loads(d.get("topics") or "[]")
            if d.get("topics")
            else []
        ),
        "attendees": json.loads(d.get("attendees") or "[]"),
        "transcript": [],
        "report": report,
        "source": f"meeting:{d['id']}",
    }


def _weekly_diaries(conn):
    rows = conn.execute(
        "SELECT agent, diary_type, content FROM agent_diaries "
        "WHERE created_at >= datetime('now','localtime','-7 days') "
        "ORDER BY id DESC LIMIT 60"
    ).fetchall()
    out = []
    for r in rows:
        content = r["content"]
        try:
            content = json.loads(content)
        except ValueError:
            pass
        out.append({"agent": r["agent"], "type": r["diary_type"], "content": content})
    return out


def _quality_and_reader(conn):
    quality = conn.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(passed),0) passed "
        "FROM quality_reports"
    ).fetchone()
    publish_failed = conn.execute(
        "SELECT COUNT(*) c FROM publish_logs WHERE result='failed' "
        "AND created_at >= datetime('now','localtime','-7 days')"
    ).fetchone()
    return {
        "quality": {"total": quality["total"] or 0, "passed": quality["passed"] or 0},
        "publish_failed_7d": publish_failed["c"] or 0,
    }


def distill(conn, meeting_id=None, session_id=None):
    mat = _meeting_material(conn, meeting_id, session_id)
    if mat is None:
        return {"ok": False, "error": "no meeting found to distill"}
    diaries = _weekly_diaries(conn)
    stats = _quality_and_reader(conn)
    prompt = (
        "你是复盘分析师。基于以下会议材料、本周 Agent 日记与质量数据，"
        "蒸馏出 2-6 条真正可执行的写作经验卡。"
        "只输出 JSON：{lessons:[{agent(建议受益的角色), title(20字内), "
        "content(2-5句，写明教训与下次具体怎么改), agents(受益角色数组), reason(依据)}]}"
        "\n会议：" + json.dumps(
            {
                "kind": mat["kind"],
                "topic": mat["topic"],
                "attendees": mat["attendees"],
                "discussion_summary": mat["report"].get("discussion_summary", ""),
                "decisions": mat["report"].get("decisions", {}),
                "action_items": mat["report"].get("action_items", []),
                "transcript_tail": (mat["transcript"] or [])[-6:],
            },
            ensure_ascii=False,
        )
        + "\n本周日记：" + json.dumps(diaries[:20], ensure_ascii=False)
        + "\n质量数据：" + json.dumps(stats, ensure_ascii=False)
    )
    resp = chat_deepseek(
        "deepseek-v4-flash", "你是复盘分析师。", prompt,
        temperature=0.3, max_tokens=2000,
    )
    parsed = _parse_json(resp["text"])
    lessons = (parsed or {}).get("lessons") or []
    if not lessons and parsed is None:
        return {"ok": False, "error": "distill output was not JSON"}
    drafted = 0
    for item in lessons:
        title = str(item.get("title") or "未命名经验").strip()
        content = str(item.get("content") or "").strip()
        if not title or not content:
            continue
        agents = item.get("agents") or []
        if isinstance(agents, str):
            agents = [agents]
        knowledge.add_draft(
            conn,
            "lesson",
            title,
            content,
            agent=str(item.get("agent") or ""),
            source=mat["source"],
            agents=[a for a in agents if a],
        )
        drafted += 1
    return {
        "ok": True,
        "meeting": mat["source"],
        "drafted": drafted,
        "total_lessons": len(lessons),
    }


def distill_latest(meeting_id=None, session_id=None, db_path=None):
    path = Path(db_path) if db_path else config.DB_PATH
    conn = db.connect(path)
    try:
        return distill(conn, meeting_id=meeting_id, session_id=session_id)
    finally:
        conn.close()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="会议反思蒸馏")
    ap.add_argument("--meeting-id", type=int, default=None)
    ap.add_argument("--session-id", type=int, default=None)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    result = distill_latest(args.meeting_id, args.session_id, args.db)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
