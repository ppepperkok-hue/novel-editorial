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
        row = None
        if args.book_id:
            row = conn.execute(
                "SELECT * FROM novels WHERE book_id=? ORDER BY id DESC LIMIT 1", (args.book_id,)
            ).fetchone()
        if row is None:
            row = conn.execute("SELECT * FROM novels ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": "no novel"}, ensure_ascii=False))
            return

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

        context = {
            "book_name": row["title"],
            "book_id": row["book_id"],
            "genre": row["genre"],
            "premise": row["premise"],
            "volume_goal": row["volume_goal"],
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
            "reader_stats": load_reader_stats(),
            "hot_topics": load_hot_topics(),
            "last_chapter_seq": summaries[-1]["seq"] if summaries else 0,
        }
        print(json.dumps({"ok": True, "context": context}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
