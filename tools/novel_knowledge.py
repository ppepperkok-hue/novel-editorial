"""Per-novel knowledge store (Karpathy-style single source of truth).

Every fact of a book lives here once, versioned and traceable: character
states, world rules, items, factions, locations, power systems, plot facts
and timeline events. Agents access it on demand via the get_novel_knowledge
tool instead of carrying the whole bible in context; updates never silently
overwrite the past (old values move to novel_knowledge_history).

CLI:
    python tools/novel_knowledge.py --sync-latest --db demo.db
    python tools/novel_knowledge.py --snapshot 1 --db demo.db
"""

import argparse
import difflib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402

CATEGORIES = ("character", "world_rule", "item", "faction", "location", "power", "plot", "timeline")
MAX_ENTITY_LEN = 16
_SENTENCE_SPLIT = re.compile(r"[:：,，。！？;；、\s]+")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_entity(category, entity):
    """Turn a raw entity string into a short stable name.

    Rules:
    - strip whitespace and surrounding quotes/brackets;
    - for characters, drop parenthesised annotations ("沈老爷子（已故）" -> "沈老爷子");
    - if the text looks like a sentence ("规则名：内容"), keep the leading name;
    - hard cap at MAX_ENTITY_LEN.
    """
    raw = str(entity or "").strip()
    if not raw:
        return ""
    for opener, closer in (("《", "》"), ("〈", "〉"), ("「", "」"), ("『", "』"), ("【", "】")):
        if raw.startswith(opener) and closer in raw:
            raw = raw.split(closer, 1)[0].lstrip(opener).strip()
            break
    if not raw:
        return ""
    if category == "character":
        raw = re.sub(r"[（(][^）)]*[）)]", "", raw).strip()
    raw = raw.strip('"\'“”‘’《》〈〉「」『』【】[]()（）')
    if not raw:
        return ""
    head = _SENTENCE_SPLIT.split(raw, 1)[0].strip()
    if head:
        raw = head.strip('"\'“”‘’《》〈〉「」『』【】[]()（）')
    if not raw:
        return ""
    return raw[:MAX_ENTITY_LEN]


def _similarity(a, b):
    return difflib.SequenceMatcher(None, a or "", b or "").ratio()


def _common_prefix_len(a, b):
    n = 0
    for x, y in zip(a or "", b or ""):
        if x != y:
            break
        n += 1
    return n


def find_similar(conn, novel_id, category, entity, limit=5):
    """Return plausible duplicates for an entity in the same category."""
    entity = normalize_entity(category, entity)
    if not entity:
        return []
    rows = conn.execute(
        "SELECT id, entity, content, version FROM novel_knowledge "
        "WHERE novel_id=? AND category=? AND entity<>? ORDER BY entity",
        (novel_id, category, entity),
    ).fetchall()
    scored = []
    for r in rows:
        ratio = _similarity(entity, r["entity"])
        prefix = _common_prefix_len(entity, r["entity"])
        if ratio >= 0.6 or (prefix >= 4 and ratio >= 0.5):
            scored.append(
                {
                    "id": r["id"],
                    "entity": r["entity"],
                    "content": (r["content"] or "")[:120],
                    "version": r["version"],
                    "ratio": round(ratio, 3),
                }
            )
    scored.sort(key=lambda x: -x["ratio"])
    return scored[:limit]


def _ensure_drafts_schema(conn):
    """Idempotently add per-novel/category columns to knowledge_drafts.

    SQLite ALTER TABLE ADD COLUMN upgrades existing databases in place;
    legacy rows keep NULL novel_id and are still matched via the title prefix.
    """
    cols = {
        r["name"]
        for r in conn.execute("PRAGMA table_info(knowledge_drafts)").fetchall()
    }
    if "novel_id" not in cols:
        conn.execute("ALTER TABLE knowledge_drafts ADD COLUMN novel_id INTEGER")
    if "category" not in cols:
        conn.execute("ALTER TABLE knowledge_drafts ADD COLUMN category TEXT DEFAULT ''")
    conn.commit()


def _add_conflict_draft(conn, novel_id, category, entity, content):
    """Write a knowledge-draft row when an entity conflicts with a similar one.

    Drafts are isolated per novel via knowledge_drafts.novel_id; legacy rows
    without a novel_id fall back to the title-prefix match.
    """
    _ensure_drafts_schema(conn)
    title = f"[小说{novel_id}] {entity}"
    existing = conn.execute(
        "SELECT id FROM knowledge_drafts WHERE kind='knowledge' "
        "AND source='auto_conflict' AND status='draft' "
        "AND (novel_id=? OR (novel_id IS NULL AND title IN (?, ?)))",
        (novel_id, title, entity),
    ).fetchone()
    if existing:
        return None
    cur = conn.execute(
        "INSERT INTO knowledge_drafts(kind,agent,source,title,content,category,novel_id,status,created_at) "
        "VALUES('knowledge','knowledge_sync','auto_conflict',?,?,?,?, 'draft', ?)",
        (title, content, category, novel_id, _now()),
    )
    return cur.lastrowid


def upsert(conn, novel_id, category, entity, content, source_chapter=None, change_note=""):
    """Idempotent upsert; returns the knowledge row id (legacy signature)."""
    result = upsert_ex(
        conn,
        novel_id,
        category,
        entity,
        content,
        source_chapter=source_chapter,
        change_note=change_note,
    )
    return result["id"]


def upsert_ex(
    conn,
    novel_id,
    category,
    entity,
    content,
    source_chapter=None,
    change_note="",
    check_similar=False,
    auto_merge=True,
):
    """Upsert with entity normalisation and optional duplicate handling.

    Returns {id, entity, merged_into, similar}. When check_similar is set,
    near-duplicate entities are merged into the existing row (versioned),
    and clearly conflicting content is queued as a knowledge draft.
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category}")
    entity = normalize_entity(category, entity)
    content = str(content or "").strip()
    if not entity or not content:
        return {"id": None, "entity": entity, "merged_into": None, "similar": []}
    row = conn.execute(
        "SELECT id, version, content FROM novel_knowledge "
        "WHERE novel_id=? AND category=? AND entity=?",
        (novel_id, category, entity),
    ).fetchone()
    if row is None:
        similar = find_similar(conn, novel_id, category, entity) if check_similar else []
        if similar and auto_merge:
            best = similar[0]
            if _similarity(content, best["content"] or "") >= 0.6:
                return {
                    **upsert_ex(
                        conn,
                        novel_id,
                        category,
                        best["entity"],
                        content,
                        source_chapter=source_chapter,
                        change_note=change_note or f"并入相似实体（原「{entity}」）",
                    ),
                    "merged_into": best["entity"],
                    "similar": similar,
                }
        if similar:
            _add_conflict_draft(conn, novel_id, category, entity, content)
        cur = conn.execute(
            "INSERT INTO novel_knowledge(novel_id,category,entity,content,source_chapter,version,updated_at) "
            "VALUES(?,?,?,?,?,1,?)",
            (novel_id, category, entity, content, source_chapter, _now()),
        )
        kid = cur.lastrowid
    else:
        kid = row["id"]
        similar = []
        if row["content"] == content:
            # Same content: idempotent upsert, no version/history churn.
            # change_note is only persisted when content actually changes.
            conn.commit()
            return {
                "id": kid,
                "entity": entity,
                "merged_into": None,
                "similar": similar,
            }
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
    return {"id": kid, "entity": entity, "merged_into": None, "similar": similar}


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


def graph(conn, novel_id, limit=80):
    """Build nodes/edges for the per-novel relationship graph.

    Nodes are knowledge entities (timeline excluded). Edges are either
    explicit (bible.relationships) or inferred co-occurrence: entity names
    mentioned inside another entity's content, or entities sharing a source
    chapter. Co-occurrence edges are kept only when they appear twice or more.
    """
    rows = conn.execute(
        "SELECT id, category, entity, content, version, source_chapter "
        "FROM novel_knowledge WHERE novel_id=? AND category<>'timeline' "
        "ORDER BY category, entity LIMIT ?",
        (novel_id, limit),
    ).fetchall()
    rows = [dict(r) for r in rows]
    by_entity = {}
    for r in rows:
        by_entity.setdefault(r["entity"], []).append(r)

    nodes = []
    seen = set()
    for r in rows:
        if r["entity"] in seen:
            continue
        seen.add(r["entity"])
        reps = by_entity[r["entity"]]
        nodes.append(
            {
                "id": r["entity"],
                "label": r["entity"],
                "category": r["category"],
                "categories": sorted({x["category"] for x in reps}),
                "version": max(x["version"] for x in reps),
                "summary": (reps[0]["content"] or "")[:120],
                "ids": [x["id"] for x in reps],
            }
        )

    edges = {}

    def add_edge(a, b, etype, label="", weight=1):
        key = tuple(sorted((a, b)))
        prev = edges.get(key)
        if prev is None:
            edges[key] = {
                "source": a,
                "target": b,
                "type": etype,
                "label": label,
                "weight": weight,
            }
            return
        if etype == "explicit":
            prev["type"] = "explicit"
            prev["label"] = label or prev["label"]
        prev["weight"] += weight

    novel = conn.execute(
        "SELECT outline FROM novels WHERE id=?", (novel_id,)
    ).fetchone()
    bible = {}
    if novel:
        try:
            bible = (json.loads(novel["outline"] or "{}") or {}).get("bible") or {}
        except ValueError:
            bible = {}
    for rel in bible.get("relationships") or []:
        if isinstance(rel, dict) and rel.get("from") and rel.get("to"):
            a = normalize_entity("character", rel["from"])
            b = normalize_entity("character", rel["to"])
            if a in by_entity and b in by_entity:
                add_edge(a, b, "explicit", str(rel.get("relation") or ""))

    names = sorted(by_entity.keys(), key=len, reverse=True)
    for r in rows:
        content = r["content"] or ""
        for name in names:
            if name != r["entity"] and name and name in content:
                add_edge(r["entity"], name, "cooccurrence")

    by_chapter = {}
    for r in rows:
        if r["source_chapter"]:
            by_chapter.setdefault(r["source_chapter"], []).append(r["entity"])
    for ents in by_chapter.values():
        uniq = sorted(set(ents))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                add_edge(uniq[i], uniq[j], "cooccurrence")

    edges_out = [
        e for e in edges.values()
        if e["type"] == "explicit" or e["weight"] >= 2
    ]
    return {"nodes": nodes, "edges": edges_out}


def _like_escape(value):
    """Escape LIKE wildcards so a literal % or _ is searched as-is."""
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def resolve(conn, novel_id, topic, limit=8):
    """Keyword search over entity and content for the agent tool."""
    topic = (topic or "").strip()
    if not topic:
        return []
    pattern = f"%{_like_escape(topic)}%"
    rows = conn.execute(
        "SELECT * FROM novel_knowledge WHERE novel_id=? "
        "AND (entity LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\') "
        "ORDER BY category, updated_at DESC LIMIT ?",
        (novel_id, pattern, pattern, limit),
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


def sync_from_chapters(conn, novel_id, limit=3):
    """Extract facts from recent chapter_summaries into the knowledge store.

    CLI: python tools/novel_knowledge.py --sync N（N 为 novel_id）
    """
    rows = conn.execute(
        "SELECT cs.chapter_id, cs.summary, cs.character_states, cs.world_events, c.seq "
        "FROM chapter_summaries cs JOIN chapters c ON c.id=cs.chapter_id "
        "WHERE c.novel_id=? ORDER BY cs.id DESC LIMIT ?",
        (novel_id, limit),
    ).fetchall()
    updated = []
    skipped = []
    for row in reversed(rows):
        cid = row["chapter_id"]
        seq = row["seq"]
        states = {}
        events = []
        try:
            states = json.loads(row["character_states"] or "{}")
        except ValueError:
            states = {}
        if not isinstance(states, dict):
            skipped.append(
                {
                    "chapter_id": cid,
                    "field": "character_states",
                    "reason": f"expected dict, got {type(states).__name__}",
                }
            )
            states = {}
        try:
            events = json.loads(row["world_events"] or "[]")
        except ValueError:
            events = []
        if not isinstance(events, list):
            skipped.append(
                {
                    "chapter_id": cid,
                    "field": "world_events",
                    "reason": f"expected list, got {type(events).__name__}",
                }
            )
            events = []
        for name, state in states.items():
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
            name = normalize_entity("character", name)
            if not name:
                continue
            kid = _upsert_if_changed(
                conn, novel_id, "character", name, str(content),
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
            entity = normalize_entity("plot", desc)
            if not entity:
                continue
            kid = _upsert_if_changed(
                conn, novel_id, "plot", entity, content,
                source_chapter=cid, change_note=f"第{seq}章·{etype}",
            )
            if kid:
                updated.append(f"plot:{entity}")
        summary = str(row["summary"] or "").strip()
        if summary:
            kid = _upsert_if_changed(
                conn, novel_id, "timeline", f"第{seq}章", summary[:200],
                source_chapter=cid, change_note=f"第{seq}章摘要",
            )
            if kid:
                updated.append(f"timeline:第{seq}章")
    return {"updated": updated, "count": len(updated), "skipped": skipped}


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _upsert_if_changed(
    conn, novel_id, category, entity, content, source_chapter=None, change_note="故事圣经初始化"
):
    """Upsert only when the stored content differs (keeps versions stable)."""
    content = str(content or "").strip()
    entity = normalize_entity(category, entity)
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
        change_note=change_note,
    )


def _outline_bible(raw):
    """Parse outline JSON defensively; fall back to an empty bible."""
    try:
        outline = json.loads(raw or "{}") or {}
    except ValueError:
        return {}, "outline 不是合法 JSON，已回退空结构"
    if not isinstance(outline, dict):
        return {}, f"outline 不是 JSON 对象（{type(outline).__name__}），已回退空结构"
    bible = outline.get("bible")
    if bible is None:
        return {}, None
    if not isinstance(bible, dict):
        return {}, "outline.bible 不是 JSON 对象，已回退空结构"
    return bible, None


def sync_from_bible(conn, novel_id, bible, source_chapter=None):
    """Initialize the per-novel knowledge store from the story bible.

    The Planner writes the first bible before chapter 1 is generated; without
    this sync the world-rule/item/power/plot categories stay empty until a
    human enters them manually (the chapter sync only covers character/plot/
    timeline). Idempotent: unchanged content is not re-versioned.
    """
    if not novel_id:
        return {"updated": [], "count": 0}
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
            title = str(rule)
            content = str(rule)
        title = normalize_entity("world_rule", title)
        if not title:
            continue
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
        name = normalize_entity("character", name)
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

    gf = str(bible.get("golden_finger") or "").strip()
    if gf:
        kid = _upsert_if_changed(conn, novel_id, "item", "金手指", gf, source_chapter)
        if kid:
            updated.append("item:金手指")

    mp = str(bible.get("main_plot") or "").strip()
    if mp:
        kid = _upsert_if_changed(conn, novel_id, "plot", "主线", mp, source_chapter)
        if kid:
            updated.append("plot:主线")

    return {"updated": updated, "count": len(updated)}


def sync_latest(conn):
    row = conn.execute(
        "SELECT c.novel_id FROM chapter_summaries cs "
        "JOIN chapters c ON c.id=cs.chapter_id ORDER BY cs.id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        # No chapters yet: still initialize the bible into the knowledge store
        # so agents can query world rules before chapter 1 is published.
        novel = conn.execute(
            "SELECT id, outline FROM novels ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if novel is None:
            return {"ok": True, "novel_id": None, "updated": [], "skipped": []}
        bible, warning = _outline_bible(novel["outline"])
        result = sync_from_bible(conn, novel["id"], bible)
        return {
            "ok": True,
            "novel_id": novel["id"],
            **result,
            "skipped": [],
            "warnings": [warning] if warning else [],
        }
    novel = conn.execute(
        "SELECT outline FROM novels WHERE id=?", (row["novel_id"],)
    ).fetchone()
    updated = []
    warnings = []
    if novel:
        bible, warning = _outline_bible(novel["outline"])
        if warning:
            warnings.append(warning)
        updated += sync_from_bible(conn, row["novel_id"], bible).get("updated", [])
    chapter_result = sync_from_chapters(conn, row["novel_id"])
    updated += chapter_result.get("updated", [])
    return {
        "ok": True,
        "novel_id": row["novel_id"],
        "updated": updated,
        "count": len(updated),
        "skipped": chapter_result.get("skipped", []),
        "warnings": warnings,
    }


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
