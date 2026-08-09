"""Weekly architect: build planning context for the Sunday blueprint meeting."""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402


def load_reader_stats():
    fp = ROOT / "demo_data" / "reader_stats.csv"
    if not fp.exists():
        return []
    rows = []
    with fp.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                rows.append(
                    {
                        "chapter": int(r["chapter"]),
                        "finish_rate": float(r["finish_rate"]),
                        "follow_rate": float(r["follow_rate"]),
                    }
                )
            except (KeyError, ValueError, TypeError):
                continue
    return rows


def load_hot_topics():
    fp = ROOT / "hot_topics.json"
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        titles = []
        for src in data.get("sources") or []:
            titles.extend(src.get("titles") or [])
        return {
            "updated_at": data.get("updated_at", ""),
            "top_keywords": data.get("top_keywords") or [],
            "titles": titles[:25],
        }
    except (OSError, ValueError):
        return {}


def build_materials(conn, novel_id):
    """Build meeting materials + per-agent weekly briefs."""
    row = conn.execute("SELECT * FROM novels WHERE id=?", (novel_id,)).fetchone()
    if row is None:
        return None
    outline = json.loads(row["outline"] or "{}")
    bible = outline.get("bible") or {}
    blueprints = outline.get("blueprints") or []

    summaries = []
    for s in conn.execute(
        "SELECT cs.summary, cs.ending_excerpt, c.seq, c.title "
        "FROM chapter_summaries cs JOIN chapters c ON c.id=cs.chapter_id "
        "WHERE c.novel_id=? ORDER BY c.seq DESC LIMIT 8",
        (row["id"],),
    ).fetchall():
        summaries.append(
            {
                "seq": s["seq"],
                "title": s["title"],
                "summary": s["summary"],
                "ending_excerpt": (s["ending_excerpt"] or "")[:120],
            }
        )
    summaries.reverse()

    threads = [
        dict(t)
        for t in conn.execute(
            "SELECT planted_chapter, expected_recover_chapter, status, description "
            "FROM plot_threads WHERE novel_id=? AND status='open' ORDER BY planted_chapter",
            (row["id"],),
        ).fetchall()
    ]

    chapters = conn.execute(
        "SELECT seq, title, status, words, score, published_at FROM chapters "
        "WHERE novel_id=? ORDER BY seq",
        (row["id"],),
    ).fetchall()
    published = [c for c in chapters if c["status"] == "published"]
    reviewed = [c for c in chapters if c["status"] == "reviewed"]
    quality = conn.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(passed),0) passed, "
        "COALESCE(AVG(c.score),0) avg_score "
        "FROM quality_reports q JOIN chapters c ON c.id=q.chapter_id "
        "WHERE c.novel_id=?",
        (row["id"],),
    ).fetchone()
    cost_row = conn.execute(
        "SELECT COALESCE(SUM(prompt_tokens),0) pt, COALESCE(SUM(completion_tokens),0) ct "
        "FROM cost_logs WHERE novel_id=? AND created_at>=date('now','localtime','start of month')",
        (row["id"],),
    ).fetchone()
    settings = {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM settings").fetchall()
    }
    char_states = [
        dict(c)
        for c in conn.execute(
            "SELECT name, role, state FROM characters WHERE novel_id=? ORDER BY id",
            (row["id"],),
        ).fetchall()
    ]
    reader_rows = load_reader_stats()
    latest_reader = reader_rows[-1] if reader_rows else None
    stock = len(reviewed)
    weekly_chapters = [
        dict(c)
        for c in chapters
        if c["published_at"] and str(c["published_at"]) >= str(row["updated_at"])[:10]
    ]

    context = {
        "book_name": row["title"],
        "book_id": row["book_id"],
        "genre": row["genre"],
        "premise": row["premise"],
        "volume_goal": row["volume_goal"],
        "status": row["status"],
        "bible": {
            "style_guide": bible.get("style_guide", ""),
            "characters": [
                {
                    "name": c.get("name"),
                    "role": c.get("role"),
                    "personality": c.get("personality"),
                    "current_state": c.get("current_state", ""),
                }
                for c in (bible.get("characters") or [])
            ],
            "world_settings": (bible.get("world_settings") or [])[:6],
            "golden_finger": bible.get("golden_finger"),
            "main_plot": bible.get("main_plot", ""),
        },
        "recent_summaries": summaries,
        "open_plot_threads": threads,
        "existing_blueprints": [
            {
                "seq": b.get("seq"),
                "title": b.get("title"),
                "outline": (b.get("outline") or "")[:150],
                "hook": b.get("hook"),
            }
            for b in blueprints
        ],
        "reader_stats": reader_rows,
        "hot_topics": load_hot_topics(),
        "last_chapter_seq": summaries[-1]["seq"] if summaries else 0,
        "published_chapters": len(published),
        "stock_chapters": stock,
        "monthly_cost_tokens": {"prompt": cost_row["pt"], "completion": cost_row["ct"]},
        "daily_chapters": int(settings.get("daily_chapters") or 2),
        "target_chapters": int(settings.get("target_chapters") or 0),
        "character_states": char_states,
        "quality_summary": {
            "total": quality["total"] or 0,
            "passed": quality["passed"] or 0,
            "avg_score": round(quality["avg_score"] or 0, 1),
        },
    }

    w = {
        "chapters_this_week": len(weekly_chapters),
        "words_total": sum(c["words"] or 0 for c in weekly_chapters),
        "avg_score": round(
            sum(c["score"] or 0 for c in weekly_chapters) / max(1, len(weekly_chapters)), 1
        ),
    }
    agent_briefs = {
        "planner": {
            "blueprints_total": len(blueprints),
            "blueprints_upcoming": sum(1 for b in blueprints if (b.get("seq") or 0) > context["last_chapter_seq"]),
            "outline_updated_at": row["updated_at"],
            "recent_summaries_count": len(summaries),
        },
        "guard": {
            "open_plot_threads": len(threads),
            "chapters_this_week": w["chapters_this_week"],
            "setting_conflicts_seen": 0,  # detailed guard issues land in the unified trace phase
        },
        "writer": {
            "chapters_this_week": w["chapters_this_week"],
            "words_total": w["words_total"],
            "avg_score": w["avg_score"],
            "quality_pass_rate": (
                round(100 * quality["passed"] / quality["total"], 1) if quality["total"] else 0
            ),
        },
        "editor": {
            "chapters_this_week": w["chapters_this_week"],
            "avg_score": w["avg_score"],
        },
        "reviewer": {
            "quality_total": quality["total"] or 0,
            "quality_passed": quality["passed"] or 0,
            "avg_score": round(quality["avg_score"] or 0, 1),
        },
        "reader": {
            "latest_finish_rate": latest_reader.get("finish_rate") if latest_reader else None,
            "latest_follow_rate": latest_reader.get("follow_rate") if latest_reader else None,
            "avg_score": round(quality["avg_score"] or 0, 1),
        },
        "memory": {
            "summaries_count": len(summaries),
            "open_plot_threads": len(threads),
            "character_state_count": len(char_states),
        },
        "work_meta": {
            "tags": json.loads(row["tags"] or "[]"),
            "abstract": row["abstract"],
            "volume_goal": row["volume_goal"],
        },
        "eic": {
            "quality_total": quality["total"] or 0,
            "quality_passed": quality["passed"] or 0,
        },
        "ending_judge": {
            "published": len(published),
            "target": int(settings.get("target_chapters") or 0),
            "open_plot_threads": len(threads),
            "last_chapter_seq": context["last_chapter_seq"],
        },
    }
    return {"context": context, "agent_briefs": agent_briefs}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="架构师周会上下文")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--book-id", default="")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        novel_id = None
        if args.book_id:
            r = conn.execute(
                "SELECT id FROM novels WHERE book_id=? ORDER BY id DESC LIMIT 1",
                (args.book_id,),
            ).fetchone()
            novel_id = r["id"] if r else None
        if novel_id is None:
            r = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
            novel_id = r["id"] if r else None
        if novel_id is None:
            print(json.dumps({"ok": False, "error": "no novel"}, ensure_ascii=False))
            return
        materials = build_materials(conn, novel_id)
        print(json.dumps({"ok": True, **materials}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
