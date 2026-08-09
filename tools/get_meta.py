"""Read the latest recorded novel metadata + memory pack from the local database.

Usage:
    python get_meta.py [book_id]
"""

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Documents\Codex\2026-08-09\new-chat-2\outputs\novel-pipeline")
DB_PATH = ROOT / "demo.db"
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from tools.app_settings import get_all  # noqa: E402


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    conn = db.connect(DB_PATH)
    try:
        book_id = sys.argv[1] if len(sys.argv) > 1 else ""
        if book_id:
            row = conn.execute(
                "SELECT * FROM novels WHERE book_id=? ORDER BY id DESC LIMIT 1", (book_id,)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM novels ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            print("{}")
            return

        outline = json.loads(row["outline"] or "{}")
        bible = outline.get("bible") or {}
        blueprints = outline.get("blueprints") or []

        hot = {}
        hot_file = ROOT / "hot_topics.json"
        if hot_file.exists():
            try:
                hot_data = json.loads(hot_file.read_text(encoding="utf-8"))
                all_titles = []
                for src in hot_data.get("sources") or []:
                    all_titles.extend(src.get("titles") or [])
                hot = {
                    "updated_at": hot_data.get("updated_at") or "",
                    "top_keywords": hot_data.get("top_keywords") or [],
                    "titles": all_titles[:30],
                }
            except (OSError, ValueError):
                hot = {}

        chapters = conn.execute(
            "SELECT id, seq, title, outline, status FROM chapters WHERE novel_id=? ORDER BY seq",
            (row["id"],),
        ).fetchall()
        last_chapter = chapters[-1] if chapters else None

        recent_summaries = []
        prev_ending = ""
        if chapters:
            ids = [c["id"] for c in chapters[-3:]]
            marks = ",".join("?" * len(ids))
            for s in conn.execute(
                "SELECT chapter_id, summary, character_states, ending_excerpt "
                "FROM chapter_summaries WHERE chapter_id IN (" + marks + ") ORDER BY id",
                ids,
            ).fetchall():
                recent_summaries.append(
                    {
                        "chapter_id": s["chapter_id"],
                        "summary": s["summary"],
                        "character_states": json.loads(s["character_states"] or "{}"),
                        "ending_excerpt": s["ending_excerpt"] or "",
                    }
                )
            prev_row = conn.execute(
                "SELECT ending_excerpt FROM chapter_summaries WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
                (last_chapter["id"],),
            ).fetchone()
            prev_ending = (prev_row["ending_excerpt"] if prev_row else "") or ""

        characters = conn.execute(
            "SELECT name, role, traits, goals, state FROM characters WHERE novel_id=? ORDER BY id",
            (row["id"],),
        ).fetchall()
        protagonists = json.loads(row["protagonists"] or "[]")
        char_states = {
            c["name"]: json.loads(c["state"] or "{}") for c in characters if c["state"]
        }
        if isinstance(bible, dict):
            for c in bible.get("characters") or []:
                st = char_states.get(c.get("name")) or {}
                if st.get("state"):
                    c["current_state"] = st["state"]

        threads = conn.execute(
            "SELECT planted_chapter, expected_recover_chapter, status, description FROM plot_threads "
            "WHERE novel_id=? AND status='open' ORDER BY planted_chapter",
            (row["id"],),
        ).fetchall()
        plot_threads = [dict(t) for t in threads]

        existing_titles = [c["title"] for c in chapters if c["title"]]
        start_seq = (chapters[-1]["seq"] + 1) if chapters else 1
        settings = get_all(conn)

        meta = {
            "book_id": row["book_id"],
            "book_name": row["title"],
            "genre": row["genre"],
            "premise": row["premise"],
            "tags": json.loads(row["tags"] or "[]"),
            "abstract": row["abstract"],
            "protagonists": protagonists,
            "volume_goal": row["volume_goal"],
            "outline": outline,
            "bible": bible,
            "blueprints": blueprints,
            "characters": [
                {
                    "name": c["name"],
                    "role": c["role"],
                    "traits": c["traits"],
                    "goals": c["goals"],
                    "state": json.loads(c["state"] or "{}"),
                }
                for c in characters
            ],
            "character_states": char_states,
            "recent_summaries": recent_summaries,
            "prev_ending": prev_ending,
            "plot_threads": plot_threads,
            "hot_topics": hot,
            "target_words": settings.get("target_words", "2000"),
            "style_tweak": settings.get("style_tweak", ""),
            "existing_titles": existing_titles,
            "start_seq": start_seq,
            "last_chapter": {
                "seq": last_chapter["seq"],
                "title": last_chapter["title"],
                "outline": last_chapter["outline"],
            }
            if last_chapter
            else None,
        }
        print(json.dumps(meta, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
