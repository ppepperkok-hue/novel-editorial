"""Write daily/weekly diaries for every agent, plus mood inference on weekly.

Daily: called after the daily run (one LLM call per agent, flash).
Weekly: called before the weekly meeting (each agent reviews the week and
writes a weekly diary; mood is inferred in the same call).
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from novel_pipeline.llm_client import chat_deepseek  # noqa: E402

AGENTS_DIR = ROOT / "prompts" / "agents"
AGENTS = [
    "planner",
    "guard",
    "writer",
    "editor",
    "reviewer",
    "reader",
    "memory",
    "work_meta",
    "eic",
    "ending_judge",
]


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


def record_cost(conn, novel_id, agent, usage, model):
    conn.execute(
        "INSERT INTO cost_logs(novel_id,node_name,model,prompt_tokens,completion_tokens,cost,created_at) "
        "VALUES(?,?,?,?,?,0,datetime('now','localtime'))",
        (
            novel_id,
            "日记:" + agent,
            model,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        ),
    )
    conn.commit()


def daily_payload(conn, novel_id):
    """Aggregate today's work data for the diary prompt."""
    chapter = conn.execute(
        "SELECT seq, title, status, words, score FROM chapters "
        "WHERE novel_id=? ORDER BY seq DESC LIMIT 1",
        (novel_id,),
    ).fetchone()
    quality = conn.execute(
        "SELECT COUNT(*) total, SUM(passed) passed FROM quality_reports q "
        "JOIN chapters c ON c.id=q.chapter_id WHERE c.novel_id=?",
        (novel_id,),
    ).fetchone()
    cost = conn.execute(
        "SELECT node_name, SUM(prompt_tokens) p, SUM(completion_tokens) c "
        "FROM cost_logs WHERE novel_id=? AND created_at>=date('now','localtime','-1 day') "
        "GROUP BY node_name ORDER BY p DESC LIMIT 12",
        (novel_id,),
    ).fetchall()
    threads = conn.execute(
        "SELECT COUNT(*) c FROM plot_threads WHERE novel_id=? AND status='open'",
        (novel_id,),
    ).fetchone()["c"]
    summaries = conn.execute(
        "SELECT cs.summary FROM chapter_summaries cs JOIN chapters c ON c.id=cs.chapter_id "
        "WHERE c.novel_id=? ORDER BY c.seq DESC LIMIT 3",
        (novel_id,),
    ).fetchall()
    return {
        "latest_chapter": dict(chapter) if chapter else None,
        "quality": {"total": quality["total"] or 0, "passed": quality["passed"] or 0},
        "cost_by_node": [dict(r) for r in cost],
        "open_plot_threads": threads,
        "recent_summaries": [s["summary"][:200] for s in summaries],
    }


def weekly_payload(conn, novel_id, agent):
    """Aggregate this week's brief + diaries + last weekly diary."""
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    diaries = conn.execute(
        "SELECT content FROM agent_diaries WHERE agent=? AND novel_id=? "
        "AND diary_type='daily' AND created_at>=? ORDER BY id",
        (agent, novel_id, since),
    ).fetchall()
    last_weekly = conn.execute(
        "SELECT content FROM agent_diaries WHERE agent=? AND novel_id=? "
        "AND diary_type='weekly' ORDER BY id DESC LIMIT 1",
        (agent, novel_id),
    ).fetchone()
    return {
        "this_week_daily_diaries": [json.loads(d["content"]) for d in diaries if d["content"]],
        "last_weekly_diary": (
            json.loads(last_weekly["content"]) if last_weekly and last_weekly["content"] else None
        ),
    }


def clean_old(conn):
    conn.execute(
        "DELETE FROM agent_diaries WHERE created_at < date('now','localtime','-56 days')"
    )
    conn.commit()


def write(conn, novel_id, mode, dry_run=False):
    results = []
    for agent in AGENTS:
        md = AGENTS_DIR / f"{agent}.md"
        if not md.exists():
            continue
        system = md.read_text(encoding="utf-8")
        if mode == "daily":
            payload = daily_payload(conn, novel_id)
            user = (
                "写今日日记。今天的工作数据：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
        else:
            payload = weekly_payload(conn, novel_id, agent)
            user = (
                "写本周日记，回顾这周我干了什么、关键事件、学到的东西、看法变化、心情变化，"
                "并额外输出 mood 字段 {satisfaction(0-1), concern(0-1), excitement(0-1), fatigue(0-1), note}。"
                "本周我的日记与上周周记：\n"
                + json.dumps(payload, ensure_ascii=False)
            )
        if dry_run:
            content = {
                "what_done": f"[dry-run] {agent} 本周工作占位",
                "observations": [],
                "feelings": "平静",
                "concerns": [],
                "thoughts": "dry-run",
            }
            usage = {"prompt_tokens": 0, "completion_tokens": 0}
            model = "dry-run"
        else:
            resp = chat_deepseek("deepseek-v4-flash", system, user, temperature=0.6, max_tokens=1200)
            content = parse_json(resp["text"]) or {"raw": resp["text"][:2000]}
            usage = resp["usage"]
            model = resp["model"]
        conn.execute(
            "INSERT INTO agent_diaries(agent,novel_id,diary_type,content,created_at) "
            "VALUES(?,?,?,?,datetime('now','localtime'))",
            (agent, novel_id, mode, json.dumps(content, ensure_ascii=False)),
        )
        if mode == "weekly":
            mood = content.get("mood") if isinstance(content, dict) else None
            if isinstance(mood, dict):
                mood.setdefault("note", "")
            else:
                mood = {"satisfaction": 0.5, "concern": 0.5, "excitement": 0.5, "fatigue": 0.3, "note": ""}
            conn.execute("DELETE FROM agent_states WHERE agent=? AND novel_id=?", (agent, novel_id))
            conn.execute(
                "INSERT INTO agent_states(agent,novel_id,mood,updated_at) "
                "VALUES(?,?,?,datetime('now','localtime'))",
                (agent, novel_id, json.dumps(mood, ensure_ascii=False)),
            )
        if not dry_run:
            record_cost(conn, novel_id, agent, usage, model)
        results.append({"agent": agent, "type": mode, "ok": True})
    clean_old(conn)
    print(json.dumps({"ok": True, "mode": mode, "written": len(results)}, ensure_ascii=False))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="为所有 Agent 写日记/周记")
    ap.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--novel-id", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        novel_id = args.novel_id
        if not novel_id:
            row = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
            novel_id = row["id"] if row else 0
        if not novel_id:
            print(json.dumps({"ok": False, "error": "no novel"}, ensure_ascii=False))
            return
        write(conn, novel_id, args.mode, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
