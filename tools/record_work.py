"""Record a finished n8n run into the local SQLite database.

Usage:
    python record_work.py <base64-json>
"""

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"E:\code\novel-pipeline")
DB_PATH = ROOT / "demo.db"
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402


def _j(value, fallback):
    try:
        return json.loads(value or fallback)
    except (TypeError, json.JSONDecodeError):
        return fallback


def upsert_novel(conn, payload):
    book_id = str(payload.get("book_id") or "")
    title = str(payload.get("book_name") or payload.get("title") or "未命名")
    genre = str(payload.get("genre") or "")
    premise = str(payload.get("premise") or "")
    selling = str(payload.get("selling_point") or "")
    tags = json.dumps(payload.get("tags") or [], ensure_ascii=False)
    abstract = str(payload.get("abstract") or "")
    protagonists = json.dumps(payload.get("protagonists") or [], ensure_ascii=False)
    volume_goal = str(payload.get("volume_goal") or "")
    updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row = None
    if book_id:
        row = conn.execute("SELECT id, outline FROM novels WHERE book_id=?", (book_id,)).fetchone()
    if row is None:
        row = conn.execute("SELECT id, outline FROM novels WHERE title=?", (title,)).fetchone()

    old_outline = _j(row["outline"], {}) if row else {}
    new_outline = payload.get("outline") or {}
    merged_outline = {**old_outline, **new_outline}
    for key in ("bible", "blueprints"):
        if key in new_outline and new_outline[key] is None:
            merged_outline.pop(key, None)
    outline = json.dumps(merged_outline, ensure_ascii=False)

    if row is None:
        cur = conn.execute(
            "INSERT INTO novels(title,genre,premise,selling_point,platform,status,"
            "book_id,tags,abstract,protagonists,outline,volume_goal,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, genre, premise, selling, "fanqie", "running",
             book_id, tags, abstract, protagonists, outline, volume_goal, updated),
        )
        novel_id = cur.lastrowid
    else:
        novel_id = row["id"]
        conn.execute(
            "UPDATE novels SET title=?,genre=?,premise=?,selling_point=?,status='running',"
            "book_id=?,tags=?,abstract=?,protagonists=?,outline=?,volume_goal=?,updated_at=? "
            "WHERE id=?",
            (title, genre, premise, selling, book_id, tags, abstract, protagonists,
             outline, volume_goal, updated, novel_id),
        )
    conn.commit()
    return novel_id


def upsert_characters(conn, novel_id, protagonists):
    conn.execute("DELETE FROM characters WHERE novel_id=?", (novel_id,))
    for i, p in enumerate(protagonists or [], start=1):
        conn.execute(
            "INSERT INTO characters(novel_id,name,role,traits,goals,first_seen_chapter) "
            "VALUES(?,?,?,?,?,?)",
            (novel_id, str(p.get("name") or "主角" + str(i)), str(p.get("role") or "主角"),
             str(p.get("traits") or ""), str(p.get("goals") or ""), 1),
        )
    conn.commit()


def upsert_volume(conn, novel_id, payload):
    row = conn.execute(
        "SELECT id FROM volumes WHERE novel_id=? AND seq=1", (novel_id,)
    ).fetchone()
    goal = str(payload.get("volume_goal") or "")
    outline = str(payload.get("premise") or "")
    if row:
        conn.execute(
            "UPDATE volumes SET goal=?,outline=? WHERE id=?",
            (goal, outline, row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO volumes(novel_id,seq,goal,outline) VALUES(?,1,?,?)",
            (novel_id, goal, outline),
        )
    conn.commit()


def _upsert_summary(conn, novel_id, chapter_id, seq, ch):
    summary = ch.get("summary") or {}
    if not summary:
        return
    summary_text = (
        summary.get("summary") if isinstance(summary, dict) else str(summary)
    ) or ""
    character_states = (
        summary.get("character_updates") if isinstance(summary, dict) else None
    ) or {}
    world_events = (
        summary.get("plot_events") if isinstance(summary, dict) else None
    ) or []
    ending_excerpt = ch.get("ending_excerpt") or ""
    exists = conn.execute(
        "SELECT id FROM chapter_summaries WHERE chapter_id=? ORDER BY id DESC LIMIT 1",
        (chapter_id,),
    ).fetchone()
    if exists:
        conn.execute(
            "UPDATE chapter_summaries SET summary=?, character_states=?, "
            "world_events=?, ending_excerpt=? WHERE id=?",
            (
                summary_text,
                json.dumps(character_states, ensure_ascii=False),
                json.dumps(world_events, ensure_ascii=False),
                ending_excerpt,
                exists["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO chapter_summaries(chapter_id,summary,character_states,"
            "world_events,ending_excerpt) VALUES(?,?,?,?,?)",
            (
                chapter_id,
                summary_text,
                json.dumps(character_states, ensure_ascii=False),
                json.dumps(world_events, ensure_ascii=False),
                ending_excerpt,
            ),
        )
    for name, state in (character_states or {}).items():
        if isinstance(state, str):
            state = {"changes": state}
        change_log = state.get("changes") or state.get("current_state") or ""
        if change_log:
            conn.execute(
                "INSERT INTO character_evolution(novel_id,chapter_id,name,snapshot,change_log,arc,created_at) "
                "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                (
                    novel_id,
                    chapter_id,
                    name,
                    json.dumps(state, ensure_ascii=False),
                    str(change_log),
                    str(state.get("arc") or ""),
                ),
            )
        c = conn.execute(
            "SELECT id, state FROM characters WHERE novel_id=? AND name=?",
            (novel_id, name),
        ).fetchone()
        if c:
            prev = _j(c["state"], {})
            prev["last_chapter"] = seq
            prev["state"] = state.get("changes") or state.get("current_state") or ""
            conn.execute(
                "UPDATE characters SET state=? WHERE id=?",
                (json.dumps(prev, ensure_ascii=False), c["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO characters(novel_id,name,role,traits,goals,state,first_seen_chapter) "
                "VALUES(?,?,?,?,?,?,?)",
                (novel_id, name, "supporting", "", "",
                 json.dumps(state, ensure_ascii=False), seq),
            )
    for ev in world_events or []:
        if not isinstance(ev, dict):
            continue
        desc = ev.get("description") or ev.get("event") or ""
        if not desc:
            continue
        conn.execute(
            "INSERT INTO world_events(novel_id,chapter_id,event,impact) VALUES(?,?,?,?)",
            (novel_id, chapter_id, desc,
             str(ev.get("importance") or ev.get("event_type") or "")),
        )
        if ev.get("event_type") in ("foreshadow", "setup") and not ev.get("resolved"):
            conn.execute(
                "INSERT INTO plot_threads(novel_id,planted_chapter,expected_recover_chapter,status,description) "
                "VALUES(?,?,?,?,?)",
                (novel_id, seq, seq + 10, "open", desc),
            )
        elif ev.get("resolved"):
            conn.execute(
                "UPDATE plot_threads SET status='closed' WHERE novel_id=? AND planted_chapter=?",
                (novel_id, seq),
            )
    for p in summary.get("foreshadowing_planted") or []:
        if not isinstance(p, dict):
            continue
        desc = str(p.get("description") or "").strip()
        if not desc:
            continue
        expected = int(p.get("expected_recover") or 0) or (seq + 10)
        conn.execute(
            "INSERT INTO plot_threads(novel_id,planted_chapter,expected_recover_chapter,status,description) "
            "VALUES(?,?,?,?,?)",
            (novel_id, seq, expected, "open", desc),
        )
    for r in summary.get("foreshadowing_recovered") or []:
        if not isinstance(r, dict):
            continue
        desc = str(r.get("description") or "").strip()
        if not desc:
            continue
        conn.execute(
            "UPDATE plot_threads SET status='closed' "
            "WHERE novel_id=? AND status='open' AND description LIKE ?",
            (novel_id, "%" + desc[:40] + "%"),
        )


def upsert_chapters(conn, novel_id, chapters):
    for ch in chapters or []:
        seq = int(ch.get("seq") or 0)
        if not seq:
            continue
        outline = str(ch.get("outline") or "")
        title = str(ch.get("title") or "")
        status = str(ch.get("status") or "published")
        words = int(ch.get("words") or 0)
        item_id = str(ch.get("fanqie_item_id") or "")
        published_at = str(ch.get("published_at") or "")
        row = conn.execute(
            "SELECT id,volume_id FROM chapters WHERE novel_id=? AND seq=?",
            (novel_id, seq),
        ).fetchone()
        vol = conn.execute(
            "SELECT id FROM volumes WHERE novel_id=? AND seq=1", (novel_id,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE chapters SET outline=?,title=?,status=?,words=?,"
                "fanqie_item_id=?,published_at=? WHERE id=?",
                (outline, title, status, words, item_id, published_at, row["id"]),
            )
            chapter_id = row["id"]
        else:
            cur = conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,words,"
                "published_at,title,fanqie_item_id) VALUES(?,?,?,?,?,?,?,?,?)",
                (novel_id, vol["id"] if vol else None, seq, outline, status, words,
                 published_at, title, item_id),
            )
            chapter_id = cur.lastrowid
        content = str(ch.get("content") or "")
        if content:
            conn.execute(
                "INSERT INTO chapter_content(chapter_id,content,updated_at) "
                "VALUES(?,?,datetime('now','localtime')) "
                "ON CONFLICT(chapter_id) DO UPDATE SET content=excluded.content, "
                "updated_at=excluded.updated_at",
                (chapter_id, content),
            )
        if status == "published":
            dup = conn.execute(
                "SELECT id FROM publish_logs WHERE chapter_id=? AND action='publish' "
                "AND result='success'",
                (chapter_id,),
            ).fetchone()
            if dup is None:
                conn.execute(
                    "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared,created_at) "
                    "VALUES(?,?,?,?,?,?,datetime('now','localtime'))",
                    (chapter_id, "fanqie", "publish", "success", None, 1),
                )
        elif status == "draft" and ch.get("error"):
            dup = conn.execute(
                "SELECT id FROM publish_logs WHERE chapter_id=? AND action='publish' "
                "AND result='failed'",
                (chapter_id,),
            ).fetchone()
            if dup is None:
                conn.execute(
                    "INSERT INTO publish_logs(chapter_id,platform,action,result,error,ai_declared) "
                    "VALUES(?,?,?,?,?,?)",
                    (chapter_id, "fanqie", "publish", "failed", ch.get("error")[:300], 1),
                )
        _upsert_summary(conn, novel_id, chapter_id, seq, ch)
    conn.commit()


def _rate_for_model(model):
    if "flash" in model:
        return float(os.environ.get("COST_FLASH_PER_1K", "0.002"))
    return float(os.environ.get("COST_PRO_PER_1K", "0.01"))


def upsert_costs(conn, novel_id, payload):
    """Record LLM token usage into cost_logs (idempotent per run is not
    critical; duplicates are bounded by manual re-runs)."""
    for c in payload.get("costs") or []:
        if not isinstance(c, dict):
            continue
        pt = int(c.get("prompt_tokens") or 0)
        ct = int(c.get("completion_tokens") or 0)
        if pt + ct <= 0:
            continue
        model = str(c.get("model") or "")
        rate = _rate_for_model(model)
        cost = round(pt / 1000.0 * rate + ct / 1000.0 * rate, 6)
        conn.execute(
            "INSERT INTO cost_logs(novel_id,node_name,model,prompt_tokens,"
            "completion_tokens,cost,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                novel_id,
                str(c.get("node") or ""),
                model,
                pt,
                ct,
                cost,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
    conn.commit()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if len(sys.argv) < 2:
        raise SystemExit("usage: record_work.py <base64-json> | --file <json-file>")
    if sys.argv[1] == "--file":
        with open(sys.argv[2], encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    conn = db.connect(DB_PATH)
    try:
        novel_id = upsert_novel(conn, payload)
        upsert_characters(conn, novel_id, payload.get("protagonists") or [])
        upsert_volume(conn, novel_id, payload)
        upsert_chapters(conn, novel_id, payload.get("chapters") or [])
        upsert_costs(conn, novel_id, payload)
        print("recorded novel_id=", novel_id, "chapters=", len(payload.get("chapters") or []))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
