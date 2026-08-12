"""Read the latest recorded novel metadata + memory pack from the local database.

Usage:
    python get_meta.py [book_id]
"""

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "demo.db"
sys.path.insert(0, str(ROOT))

from novel_editorial import config, data_feedback, db  # noqa: E402
from tools.app_settings import get_all  # noqa: E402
from tools import novel_knowledge  # noqa: E402


def _safe_json(value, fallback, field):
    """Parse JSON with a default fallback; dirty JSON (including valid JSON
    of the wrong shape) is replaced and logged instead of crashing the CLI."""
    try:
        parsed = json.loads(value or fallback)
    except (TypeError, ValueError):
        parsed = None
    if not isinstance(parsed, type(fallback)):
        parsed = fallback
        try:
            with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                    f"get_meta: {field} 非合法 JSON（或类型不符），使用默认值\n"
                )
        except OSError:
            pass
    return parsed


def _trace(message):
    """Append a trace line to alerts.log; I/O failure must not crash the CLI."""
    try:
        with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    import argparse

    ap = argparse.ArgumentParser(description="读取本地作品资料与记忆包")
    ap.add_argument("book_id", nargs="?", default="")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        book_id = args.book_id
        if book_id:
            row = conn.execute(
                "SELECT * FROM novels WHERE book_id=? ORDER BY id DESC LIMIT 1", (book_id,)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM novels ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            print("{}")
            return

        outline = _safe_json(row["outline"] or "{}", {}, "outline")
        bible = outline.get("bible") or {}
        blueprints = outline.get("blueprints") or []

        hot = {}
        hot_file = config.HOT_TOPICS_JSON
        if hot_file.exists():
            try:
                hot_data = json.loads(hot_file.read_text(encoding="utf-8"))
                if not isinstance(hot_data, dict):
                    hot_data = None
                    try:
                        with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                            f.write(
                                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                                "get_meta: hot_topics.json 非法结构（非对象），使用默认值\n"
                            )
                    except OSError:
                        pass
                if hot_data is not None:
                    sources = hot_data.get("sources") or []
                    if not isinstance(sources, list):
                        _trace("get_meta: hot_topics.sources 非 list，已回退为空")
                        sources = []
                    all_titles = []
                    for src in sources:
                        if not isinstance(src, dict):
                            _trace(
                                f"get_meta: hot_topics.sources 元素 "
                                f"({type(src).__name__}) 非 dict，已跳过"
                            )
                            continue
                        titles = src.get("titles") or []
                        if not isinstance(titles, list):
                            _trace(
                                "get_meta: hot_topics.sources.titles 非 list，已跳过"
                            )
                            titles = []
                        all_titles.extend(titles)
                    top_keywords = hot_data.get("top_keywords") or []
                    if not isinstance(top_keywords, list):
                        _trace("get_meta: hot_topics.top_keywords 非 list，已回退为空")
                        top_keywords = []
                    hot = {
                        "updated_at": hot_data.get("updated_at") or "",
                        "top_keywords": top_keywords,
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
                        "character_states": _safe_json(
                            s["character_states"] or "{}", {}, "character_states"
                        ),
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
        protagonists = _safe_json(row["protagonists"] or "[]", [], "protagonists")
        char_states = {
            c["name"]: _safe_json(
                c["state"] or "{}", {}, f"characters[{c['name']}].state"
            )
            for c in characters
            if c["state"]
        }
        if isinstance(bible, dict):
            for c in bible.get("characters") or []:
                if not isinstance(c, dict):
                    try:
                        with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                            f.write(
                                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                                f"get_meta: bible.characters 元素类型 "
                                f"{type(c).__name__}，已跳过\n"
                            )
                    except OSError:
                        pass
                    continue
                st = char_states.get(c.get("name")) or {}
                if st.get("state"):
                    c["current_state"] = st["state"]

        threads = conn.execute(
            "SELECT planted_chapter, expected_recover_chapter, status, description FROM plot_threads "
            "WHERE novel_id=? AND status='open' ORDER BY planted_chapter",
            (row["id"],),
        ).fetchall()
        plot_threads = [dict(t) for t in threads]

        evolution = [
            dict(e)
            for e in conn.execute(
                "SELECT name, chapter_id, change_log, arc, created_at "
                "FROM character_evolution WHERE novel_id=? "
                "ORDER BY id DESC LIMIT 10",
                (row["id"],),
            ).fetchall()
        ]
        evolution.reverse()

        existing_titles = [c["title"] for c in chapters if c["title"]]
        start_seq = (chapters[-1]["seq"] + 1) if chapters else 1
        settings = get_all(conn)
        reader_feedback = {}
        reader_csv = config.READER_CSV
        if reader_csv.exists():
            try:
                rows = data_feedback.load_reader_stats(reader_csv)
                if rows:
                    report = data_feedback.feedback_report(rows)
                    reader_feedback = {
                        "low_chapters": report.get("low_chapters") or [],
                        "avg_finish": report.get("avg_finish"),
                        "avg_follow": report.get("avg_follow"),
                        "chapters": report.get("chapters"),
                    }
            except (OSError, ValueError):
                reader_feedback = {}

        tags = _safe_json(row["tags"] or "[]", [], "tags")
        if any(not isinstance(t, str) for t in tags):
            tags = []
            try:
                with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
                    f.write(
                        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
                        f"get_meta: tags 含非字符串元素，已回退默认值\n"
                    )
            except OSError:
                pass
        meta = {
            "novel_id": row["id"],
            "book_id": row["book_id"],
            "book_name": row["title"],
            "genre": row["genre"],
            "premise": row["premise"],
            "tags": tags,
            "keywords": ",".join(tags),
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
                    "state": _safe_json(
                        c["state"] or "{}", {}, f"characters[{c['name']}].state"
                    ),
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
            "reader_feedback": reader_feedback,
            "existing_titles": existing_titles,
            "start_seq": start_seq,
            "finish_status": row["status"],
            "finish_remaining": row["finish_remaining"],
            "target_chapters": row["target_chapters"],
            "character_evolution": evolution,
            "novel_knowledge": novel_knowledge.snapshot(conn, row["id"]),
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
