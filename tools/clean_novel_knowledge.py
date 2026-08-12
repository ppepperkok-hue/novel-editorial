"""One-shot cleanup for the per-novel knowledge store.

Scans every novel's knowledge rows and plans:
1. entity normalisation (sentence-style names -> short names);
2. merge of "角色·状态" rows back into the character entity;
3. removal of the duplicated golden-finger under power (item wins);
4. merge of near-duplicate world_rule rows.

Default is --dry-run (prints the plan, writes nothing). Pass --apply to
execute; a database backup is written to backups/ before applying.

Run from the pipeline root:
    python tools/clean_novel_knowledge.py --dry-run
    python tools/clean_novel_knowledge.py --apply
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402
from tools.novel_knowledge import (  # noqa: E402
    _common_prefix_len,
    _similarity,
    normalize_entity,
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _plan_renames(conn):
    """Rows whose entity differs from its normalised form."""
    out = []
    for r in conn.execute(
        "SELECT id, novel_id, category, entity FROM novel_knowledge"
    ).fetchall():
        norm = normalize_entity(r["category"], r["entity"])
        if not norm or norm == r["entity"]:
            continue
        conflict = conn.execute(
            "SELECT id FROM novel_knowledge WHERE novel_id=? AND category=? "
            "AND entity=? AND id<>?",
            (r["novel_id"], r["category"], norm, r["id"]),
        ).fetchone()
        out.append(
            {
                "kind": "rename",
                "id": r["id"],
                "novel_id": r["novel_id"],
                "category": r["category"],
                "from": r["entity"],
                "to": norm,
                "merge_into": conflict["id"] if conflict else None,
            }
        )
    return out


def _plan_state_rows(conn):
    """'角色·状态' rows merge back into the plain character entity."""
    out = []
    rows = conn.execute(
        "SELECT id, novel_id, entity FROM novel_knowledge "
        "WHERE category='character' AND entity LIKE '%·%'"
    ).fetchall()
    for r in rows:
        name = r["entity"].rsplit("·", 1)[0].strip()
        if not name:
            continue
        target = conn.execute(
            "SELECT id FROM novel_knowledge WHERE novel_id=? AND category='character' "
            "AND entity=? AND id<>?",
            (r["novel_id"], name, r["id"]),
        ).fetchone()
        out.append(
            {
                "kind": "merge_state",
                "id": r["id"],
                "novel_id": r["novel_id"],
                "from": r["entity"],
                "to": name,
                "merge_into": target["id"] if target else None,
            }
        )
    return out


def _plan_dup_golden_finger(conn):
    """power/金手指 duplicates are dropped; item/金手指 wins."""
    out = []
    for r in conn.execute(
        "SELECT id, novel_id FROM novel_knowledge "
        "WHERE category='power' AND entity='金手指'"
    ).fetchall():
        item = conn.execute(
            "SELECT id FROM novel_knowledge WHERE novel_id=? "
            "AND category='item' AND entity='金手指'",
            (r["novel_id"],),
        ).fetchone()
        out.append(
            {
                "kind": "drop_dup_golden_finger",
                "id": r["id"],
                "novel_id": r["novel_id"],
                "keep_id": item["id"] if item else None,
                # No item/金手指 row exists: keep the unique power record by
                # reclassifying it under item instead of deleting it (R12-C-03).
                "keep_as": "item" if item is None else None,
            }
        )
    return out


def _plan_similar_rules(conn):
    """Merge near-duplicate world_rule rows within the same novel.

    Similar pairs are grouped with union-find so chained rules (A~B~C) are
    planned as one keep row absorbing every other row. Applying a chained plan
    in order would delete a row that is still referenced as a later keep
    target and silently drop its content (R12-C-02).
    """
    out = []
    novels = conn.execute(
        "SELECT DISTINCT novel_id FROM novel_knowledge WHERE category='world_rule'"
    ).fetchall()
    for (nid,) in novels:
        rows = conn.execute(
            "SELECT id, entity, content, version, updated_at FROM novel_knowledge "
            "WHERE novel_id=? AND category='world_rule' ORDER BY entity",
            (nid,),
        ).fetchall()
        parent = {}

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a["entity"] == b["entity"]:
                    continue
                ratio = _similarity(a["entity"], b["entity"])
                prefix = _common_prefix_len(a["entity"], b["entity"])
                if ratio >= 0.7 or (prefix >= 6 and ratio >= 0.55):
                    union(a["id"], b["id"])
        groups = {}
        for r in rows:
            groups.setdefault(find(r["id"]), []).append(r)
        for members in groups.values():
            if len(members) < 2:
                continue
            keep = max(members, key=lambda r: r["version"])
            for drop in members:
                if drop["id"] == keep["id"]:
                    continue
                out.append(
                    {
                        "kind": "merge_similar_rule",
                        "novel_id": nid,
                        "keep_id": keep["id"],
                        "keep_entity": keep["entity"],
                        "drop_id": drop["id"],
                        "drop_entity": drop["entity"],
                        "ratio": round(_similarity(keep["entity"], drop["entity"]), 3),
                    }
                )
    return out


def _plan_misclassified(conn):
    """Drop legacy rows that no longer belong in the knowledge store.

    - plot/人物关系 now lives in bible.relationships (graph explicit edges);
    - world_rule/文风 lives in bible.style_guide.
    """
    out = []
    for r in conn.execute(
        "SELECT id, novel_id, category, entity FROM novel_knowledge "
        "WHERE (category='plot' AND entity='人物关系') "
        "OR (category='world_rule' AND entity='文风')"
    ).fetchall():
        out.append(
            {
                "kind": "drop_misclassified",
                "id": r["id"],
                "novel_id": r["novel_id"],
                "category": r["category"],
                "entity": r["entity"],
            }
        )
    return out


def plan_clean(conn):
    return {
        "renames": _plan_renames(conn),
        "state_rows": _plan_state_rows(conn),
        "golden_finger_dups": _plan_dup_golden_finger(conn),
        "similar_rules": _plan_similar_rules(conn),
        "misclassified": _plan_misclassified(conn),
    }


def _merge_history(conn, keep_id, drop_id):
    if keep_id == drop_id:
        return
    keep = conn.execute(
        "SELECT id, content, version FROM novel_knowledge WHERE id=?", (keep_id,)
    ).fetchone()
    if keep is None:
        # Chained plan referenced a keep row already removed: drop safely.
        conn.execute(
            "DELETE FROM novel_knowledge_history WHERE knowledge_id=?",
            (drop_id,),
        )
        conn.execute("DELETE FROM novel_knowledge WHERE id=?", (drop_id,))
        return
    drop = conn.execute(
        "SELECT id, content, entity FROM novel_knowledge WHERE id=?", (drop_id,)
    ).fetchone()
    if drop is None:
        return
    keep_content = str(keep["content"] or "").strip()
    drop_content = str(drop["content"] or "").strip()
    if drop_content and drop_content != keep_content:
        # Preserve the dropped row's content instead of silently losing it:
        # append it to the keep row and version the merge for traceability.
        merged = drop_content if not keep_content else f"{keep_content}\n\n{drop_content}"
        if keep_content:
            conn.execute(
                "INSERT OR IGNORE INTO novel_knowledge_history("
                "knowledge_id,content,version,change_note,created_at) "
                "VALUES(?,?,?,?,?)",
                (keep_id, keep_content, keep["version"], f"merged:{drop['entity']}", _now()),
            )
        conn.execute(
            "UPDATE novel_knowledge SET content=?, version=version+1, updated_at=? WHERE id=?",
            (merged, _now(), keep_id),
        )
    drop_history = conn.execute(
        "SELECT content, version, change_note, created_at "
        "FROM novel_knowledge_history WHERE knowledge_id=?",
        (drop_id,),
    ).fetchall()
    for h in drop_history:
        # Move each history row to the keep row. INSERT OR IGNORE skips a
        # version already present on the keep side (keeps the unique
        # knowledge_id/version guard from R12-C-01 intact).
        conn.execute(
            "INSERT OR IGNORE INTO novel_knowledge_history("
            "knowledge_id,content,version,change_note,created_at) VALUES(?,?,?,?,?)",
            (keep_id, h["content"], h["version"], h["change_note"], h["created_at"]),
        )
    conn.execute(
        "DELETE FROM novel_knowledge_history WHERE knowledge_id=?", (drop_id,)
    )
    conn.execute("DELETE FROM novel_knowledge WHERE id=?", (drop_id,))


def apply_clean(conn, plan):
    for item in plan["renames"]:
        if item["merge_into"]:
            _merge_history(conn, item["merge_into"], item["id"])
        else:
            conflict = conn.execute(
                "SELECT id FROM novel_knowledge WHERE novel_id=? AND category=? "
                "AND entity=? AND id<>?",
                (item["novel_id"], item["category"], item["to"], item["id"]),
            ).fetchone()
            if conflict:
                # Several entities converged to the same canonical name and an
                # earlier rename already created it: merge instead of crashing
                # on the UNIQUE constraint.
                _merge_history(conn, conflict["id"], item["id"])
                continue
            conn.execute(
                "UPDATE novel_knowledge SET entity=? WHERE id=?",
                (item["to"], item["id"]),
            )
    for item in plan["state_rows"]:
        if item["merge_into"]:
            _merge_history(conn, item["merge_into"], item["id"])
        else:
            conflict = conn.execute(
                "SELECT id FROM novel_knowledge WHERE novel_id=? AND category=? "
                "AND entity=? AND id<>?",
                (item["novel_id"], "character", item["to"], item["id"]),
            ).fetchone()
            if conflict:
                _merge_history(conn, conflict["id"], item["id"])
                continue
            conn.execute(
                "UPDATE novel_knowledge SET entity=? WHERE id=?",
                (item["to"], item["id"]),
            )
    for item in plan["golden_finger_dups"]:
        if item["keep_id"]:
            _merge_history(conn, item["keep_id"], item["id"])
        elif item.get("keep_as"):
            # No item/金手指 row exists: preserve the unique power record
            # under item instead of silently deleting it (R12-C-03).
            conn.execute(
                "UPDATE novel_knowledge SET category=?, updated_at=? WHERE id=?",
                (item["keep_as"], _now(), item["id"]),
            )
        else:
            conn.execute(
                "DELETE FROM novel_knowledge_history WHERE knowledge_id=?",
                (item["id"],),
            )
            conn.execute("DELETE FROM novel_knowledge WHERE id=?", (item["id"],))
    for item in plan["similar_rules"]:
        _merge_history(conn, item["keep_id"], item["drop_id"])
    for item in plan["misclassified"]:
        conn.execute(
            "DELETE FROM novel_knowledge_history WHERE knowledge_id=?",
            (item["id"],),
        )
        conn.execute("DELETE FROM novel_knowledge WHERE id=?", (item["id"],))
    conn.commit()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Clean the per-novel knowledge store")
    ap.add_argument("--db", default=None)
    ap.add_argument("--dry-run", action="store_true", help="只报告不落库（默认行为）")
    ap.add_argument("--apply", action="store_true", help="actually apply the plan")
    args = ap.parse_args()
    if args.apply and args.dry_run:
        raise SystemExit("--dry-run 与 --apply 不能同时使用")
    dry_run = args.dry_run or not args.apply
    path = Path(args.db) if args.db else config.DB_PATH
    conn = db.connect(path)
    try:
        plan = plan_clean(conn)
        counts = {k: len(v) for k, v in plan.items()}
        if dry_run:
            print(json.dumps({"dry_run": dry_run, "counts": counts, "plan": plan}, ensure_ascii=False, indent=1))
            return
        backup_dir = ROOT / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_dir / f"{path.stem}-{stamp}.db"
        backup_conn = sqlite3.connect(backup)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()
        apply_clean(conn, plan)
        print(json.dumps({"applied": True, "backup": str(backup), "counts": counts}, ensure_ascii=False, indent=1))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
