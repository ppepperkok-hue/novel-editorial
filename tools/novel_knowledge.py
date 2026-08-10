"""Per-novel knowledge store (Karpathy-style single source of truth).

Every fact of a book lives here once, versioned and traceable: character
states, world rules, items, factions, locations, power systems, plot facts
and timeline events. Agents access it on demand via the get_novel_knowledge
tool instead of carrying the whole bible in context; updates never silently
overwrite the past (old values move to novel_knowledge_history).

CLI:
    python tools/novel_knowledge.py --sync-latest --db demo.db
    python tools/novel_knowledge.py --snapshot --novel-id 1 --db demo.db
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402

CATEGORIES = ("character", "world_rule", "item", "faction", "location", "power", "plot", "timeline")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def upsert(conn, novel_id, category, entity, content, source_chapter=None, change_note=""):
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category}")
    entity = str(entity or "").strip()
    content = str(content or "").strip()
    if not entity or not content:
        return None
    row = conn.execute(
        "SELECT id, version, content FROM novel_knowledge "
        "WHERE novel_id=? AND category=? AND entity=?",
        (novel_id, category, entity),
    ).fetchone()
    if row is None:
        cur = conn.execute(
            "INSERT INTO novel_knowledge(novel_id,category,entity,content,source_chapter,version,updated_at) "
            "VALUES(?,?,?,?,?,1,?)",
            (novel_id, category, entity, content, source_chapter, _now()),
        )
        kid = cur.lastrowid
    else:
        kid = row["id"]
        old_version = row["version"]
        conn.execute(
            "INSERT INTO novel_knowledge_history(knowledge_id,content,version,change_note,created_at) "
            "VALUES(?,?,?,?,?)",
            (kid, row["content"], old_version, change_note, _now()),
        )
        conn.execute(
            "UPDATE novel_knowledge SET content=?, source_chapter=?, version=version+1, updated_at=? "
            "WHERE id=?",
            (content, source_chapter, _now(), kid),
        )
    conn.commit()
    return kid


def get(conn, novel_id, category=None, entity=None, limit=300):
    sql = "SELECT * FROM novel_knowledge WHERE novel_id=?"
    args = [novel_id]
    if category:
        sql += " AND category=?"
        args.append(category)
    if entity:
        sql += " AND entity LIKE ?"
        args.append(f"%{entity}%")
    sql += " ORDER BY category, entity LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def history(conn, knowledge_id, limit=20):
    rows = conn.execute(
        "SELECT * FROM novel_knowledge_history WHERE knowledge_id=? "
        "ORDER BY version DESC LIMIT ?",
        (knowledge_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve(conn, novel_id, topic, limit=8):
    """Keyword search over entity and content for the agent tool."""
    topic = (topic or "").strip()
    if not topic:
        return []
    rows = conn.execute(
        "SELECT * FROM novel_knowledge WHERE novel_id=? "
        "AND (entity LIKE ? OR content LIKE ?) ORDER BY category, updated_at DESC LIMIT ?",
        (novel_id, f"%{topic}%", f"%{topic}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def snapshot(conn, novel_id, per_category=6, max_len=180):
    """Compact per-category digest for context injection."""
    out = []
    for cat in CATEGORIES:
        rows = conn.execute(
            "SELECT entity, content, version FROM novel_knowledge "
            "WHERE novel_id=? AND category=? ORDER BY updated_at DESC LIMIT ?",
            (novel_id, cat, per_category),
        ).fetchall()
        for r in rows:
            out.append(
                {
                    "category": cat,
                    "entity": r["entity"],
                    "content": (r["content"] or "")[:max_len],
                    "version": r["version"],
                }
            )
    return out


def sync_from_chapters(conn, novel_id, chapter_id=None, limit=3):
    """Extract facts from recent chapter_summaries into the knowledge store."""
    rows = conn.execute(
        "SELECT cs.chapter_id, cs.summary, cs.character_states, cs.world_events, c.seq "
        "FROM chapter_summaries cs JOIN chapters c ON c.id=cs.chapter_id "
        "WHERE c.novel_id=? ORDER BY cs.id DESC LIMIT ?",
        (novel_id, limit),
    ).fetchall()
    updated = []
    for row in reversed(rows):
        cid = row["chapter_id"]
        seq = row["seq"]
        states = {}
        events = []
        try:
            states = json.loads(row["character_states"] or "{}")
        except ValueError:
            states = {}
        try:
            events = json.loads(row["world_events"] or "[]")
        except ValueError:
            events = []
        for name, state in (states or {}).items():
            if isinstance(state, str):
                state = {"current_state": state}
            if not isinstance(state, dict):
                continue
            content = (
                state.get("current_state")
                or state.get("changes")
                or state.get("state")
                or ""
            )
            if not content:
                continue
            kid = upsert(
                conn, novel_id, "character", str(name), str(content),
                source_chapter=cid, change_note=f"第{seq}章",
            )
            if kid:
                updated.append(f"character:{name}")
        for ev in events or []:
            if not isinstance(ev, dict):
                continue
            desc = str(ev.get("description") or "").strip()
            if not desc:
                continue
            etype = str(ev.get("event_type") or "plot")
            importance = ev.get("importance") or ""
            resolved = ev.get("resolved")
            content = desc
            if importance:
                content += f"（重要度{importance}）"
            if resolved is not None:
                content += "（已解决）" if resolved else "（未解决）"
            entity = desc[:24]
            kid = upsert(
                conn, novel_id, "plot", entity, content,
                source_chapter=cid, change_note=f"第{seq}章·{etype}",
            )
            if kid:
                updated.append(f"plot:{entity}")
        summary = str(row["summary"] or "").strip()
        if summary:
            kid = upsert(
                conn, novel_id, "timeline", f"第{seq}章", summary[:200],
                source_chapter=cid, change_note=f"第{seq}章摘要",
            )
            if kid:
                updated.append(f"timeline:第{seq}章")
    return {"updated": updated, "count": len(updated)}


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _upsert_if_changed(conn, novel_id, category, entity, content, source_chapter=None):
    """Upsert only when the stored content differs (keeps versions stable)."""
    content = str(content or "").strip()
    if not entity or not content:
        return None
    row = conn.execute(
        "SELECT id, content FROM novel_knowledge "
        "WHERE novel_id=? AND category=? AND entity=?",
        (novel_id, category, entity),
    ).fetchone()
    if row and str(row["content"] or "").strip() == content:
        return None
    return upsert(
        conn, novel_id, category, entity, content,
        source_chapter=source_chapter,
        change_note="故事圣经初始化",
    )


def sync_from_bible(conn, novel_id, bible, source_chapter=None):
    """Initialize the per-novel knowledge store from the story bible.

    The Planner writes the first bible before chapter 1 is generated; without
    this sync the world-rule/item/power/plot categories stay empty until a
    human enters them manually (the chapter sync only covers character/plot/
    timeline). Idempotent: unchanged content is not re-versioned.
    """
    bible = bible or {}
    updated = []

    for i, rule in enumerate(_as_list(bible.get("world_rules")), start=1):
        if isinstance(rule, dict):
            title = str(rule.get("rule") or rule.get("name") or f"规则{i}")[:40]
            content = str(
                rule.get("content")
                or rule.get("description")
                or rule.get("detail")
                or ""
            )
            if not content.strip():
                content = str(rule)
        else:
            title = str(rule)[:24]
            content = str(rule)
        kid = _upsert_if_changed(
            conn, novel_id, "world_rule", title, content, source_chapter
        )
        if kid:
            updated.append(f"world_rule:{title}")

    for c in _as_list(bible.get("characters")):
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        parts = []
        for key in ("identity", "personality", "speech_style", "ooc_redline",
                    "current_state", "goals"):
            value = c.get(key)
            if value:
                parts.append(f"{key}: {value}")
        content = "；".join(parts)
        kid = _upsert_if_changed(
            conn, novel_id, "character", name, content, source_chapter
        )
        if kid:
            updated.append(f"character:{name}")

    rel_text = "；".join(
        f"{r.get('from')}→{r.get('to')}({r.get('relation', '')})"
        for r in _as_list(bible.get("relationships"))
        if isinstance(r, dict) and r.get("from") and r.get("to")
    )
    if rel_text:
        kid = _upsert_if_changed(
            conn, novel_id, "plot", "人物关系", rel_text, source_chapter
        )
        if kid:
            updated.append("plot:人物关系")

    gf = str(bible.get("golden_finger") or "").strip()
    if gf:
        kid = _upsert_if_changed(conn, novel_id, "item", "金手指", gf, source_chapter)
        if kid:
            updated.append("item:金手指")
        kid = _upsert_if_changed(conn, novel_id, "power", "金手指", gf, source_chapter)
        if kid:
            updated.append("power:金手指")

    mp = str(bible.get("main_plot") or "").strip()
    if mp:
        kid = _upsert_if_changed(conn, novel_id, "plot", "主线", mp, source_chapter)
        if kid:
            updated.append("plot:主线")

    sg = str(bible.get("style_guide") or "").strip()
    if sg:
        kid = _upsert_if_changed(
            conn, novel_id, "world_rule", "文风", sg, source_chapter
        )
        if kid:
            updated.append("world_rule:文风")

    return {"updated": updated, "count": len(updated)}


def sync_latest(conn):
    row = conn.execute(
        "SELECT DISTINCT c.novel_id FROM chapter_summaries cs "
        "JOIN chapters c ON c.id=cs.chapter_id ORDER BY cs.id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        # No chapters yet: still initialize the bible into the knowledge store
        # so agents can query world rules before chapter 1 is published.
        novel = conn.execute(
            "SELECT id, outline FROM novels ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if novel is None:
            return {"ok": True, "novel_id": None, "updated": []}
        bible = (json.loads(novel["outline"] or "{}") or {}).get("bible") or {}
        return {
            "ok": True,
            "novel_id": novel["id"],
            **sync_from_bible(conn, novel["id"], bible),
        }
    novel = conn.execute(
        "SELECT outline FROM novels WHERE id=?", (row["novel_id"],)
    ).fetchone()
    updated = []
    if novel:
        bible = (json.loads(novel["outline"] or "{}") or {}).get("bible") or {}
        updated += sync_from_bible(conn, row["novel_id"], bible).get("updated", [])
    updated += sync_from_chapters(conn, row["novel_id"]).get("updated", [])
    return {"ok": True, "novel_id": row["novel_id"], "updated": updated}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="每部小说的设定知识库")
    ap.add_argument("--db", default=None)
    ap.add_argument("--sync-latest", action="store_true")
    ap.add_argument("--sync", type=int, default=None, metavar="NOVEL_ID")
    ap.add_argument("--snapshot", type=int, default=None, metavar="NOVEL_ID")
    ap.add_argument("--upsert", nargs=4, metavar=("NOVEL_ID", "CATEGORY", "ENTITY", "CONTENT"))
    ap.add_argument("--sync-bible", metavar="FILE", default=None)
    args = ap.parse_args()
    path = Path(args.db) if args.db else config.DB_PATH
    conn = db.connect(path)
    try:
        if args.sync_latest:
            result = sync_latest(conn)
        elif args.sync_bible:
            payload = json.loads(Path(args.sync_bible).read_text(encoding="utf-8"))
            book_id = str(payload.get("book_id") or "")
            novel_id = 0
            if book_id:
                r = conn.execute(
                    "SELECT id FROM novels WHERE book_id=? ORDER BY id DESC LIMIT 1",
                    (book_id,),
                ).fetchone()
                novel_id = r["id"] if r else 0
            if not novel_id:
                r = conn.execute("SELECT id FROM novels ORDER BY id DESC LIMIT 1").fetchone()
                novel_id = r["id"] if r else 0
            result = {
                "ok": True,
                "novel_id": novel_id,
                **sync_from_bible(conn, novel_id, payload.get("bible") or {}),
            }
        elif args.sync is not None:
            result = sync_from_chapters(conn, args.sync)
        elif args.snapshot is not None:
            result = {"ok": True, "items": snapshot(conn, args.snapshot)}
        elif args.upsert:
            kid = upsert(conn, *[int(args.upsert[0]), args.upsert[1], args.upsert[2], args.upsert[3]])
            result = {"ok": True, "id": kid}
        else:
            raise SystemExit("请指定 --sync-latest / --sync N / --snapshot N / --upsert")
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
