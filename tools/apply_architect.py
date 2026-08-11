"""Apply the weekly architect output back into the novel outline."""

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import db  # noqa: E402
from novel_editorial.services import audit  # noqa: E402


def merge_blueprints(old, updates):
    by_seq = {int(b.get("seq") or 0): b for b in old if b.get("seq")}
    for u in updates or []:
        seq = int(u.get("seq") or 0)
        if not seq:
            continue
        by_seq[seq] = {**by_seq.get(seq, {}), **u}
    return [by_seq[k] for k in sorted(by_seq)]


def create_planning_from_next_book(conn, report, cover_prompt=""):
    """Create a planning novel from a new-book meeting (no novel yet).

    Used when a topic/new-book meeting produces decisions.next_book while no
    work exists: the conclusion becomes a planning novel so the panel can
    then run auto-create on Fanqie. Idempotent by title.
    """
    decisions = report.get("decisions") or {}
    next_book = decisions.get("next_book")
    if not isinstance(next_book, dict) or not str(next_book.get("book_name") or "").strip():
        return {"ok": False, "reason": "report has no next_book"}
    cover_prompt = str(cover_prompt or report.get("cover_prompt") or "").strip()
    title = str(next_book["book_name"]).strip()[:50]
    dup = conn.execute(
        "SELECT id FROM novels WHERE title=? AND status='planning'", (title,)
    ).fetchone()
    if dup is not None:
        return {"ok": True, "id": dup["id"], "duplicate": True}
    existing = conn.execute(
        "SELECT id FROM novels WHERE status='planning' LIMIT 1"
    ).fetchone()
    if existing is not None:
        return {"ok": True, "skipped": True, "reason": "已有待确认的规划新书，暂不重复孵化"}
    protagonists = json.dumps(
        [
            {
                "name": str(next_book.get("protagonist") or "主角").strip()[:20] or "主角",
                "role": "主角",
            }
        ],
        ensure_ascii=False,
    )
    cur = conn.execute(
        "INSERT INTO novels(title,genre,premise,selling_point,platform,status,"
        "abstract,protagonists,cover_prompt,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
        (
            title,
            str(next_book.get("genre") or "都市").strip()[:20] or "都市",
            str(next_book.get("abstract") or next_book.get("premise") or ""),
            str(next_book.get("selling_point") or ""),
            "fanqie",
            "planning",
            str(next_book.get("abstract") or ""),
            protagonists,
            str(cover_prompt or ""),
        ),
    )
    conn.commit()
    return {"ok": True, "id": cur.lastrowid, "duplicate": False}


def persist_character_updates(conn, novel_id, char_updates):
    """Persist weekly character_updates into characters/character_evolution.

    Idempotent: an evolution row is only added when the exact change_log has
    not been recorded before. Weekly entries carry chapter_id=0.
    """
    if not isinstance(char_updates, list) or not char_updates:
        return {"ok": True, "updated": 0}
    updated = 0
    try:
        for u in char_updates:
            if not isinstance(u, dict):
                continue
            name = str(u.get("name") or "").strip()
            if not name:
                continue
            change_log = str(u.get("change_log") or u.get("current_state") or "").strip()
            row = conn.execute(
                "SELECT id, state FROM characters WHERE novel_id=? AND name=?",
                (novel_id, name),
            ).fetchone()
            if row:
                prev = json.loads(row["state"] or "{}")
                if u.get("current_state"):
                    prev["current_state"] = str(u["current_state"])
                if change_log:
                    prev["last_weekly_change"] = change_log
                conn.execute(
                    "UPDATE characters SET state=? WHERE id=?",
                    (json.dumps(prev, ensure_ascii=False), row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO characters(novel_id,name,role,traits,goals,state,first_seen_chapter) "
                    "VALUES(?,?,?,?,?,?,0)",
                    (
                        novel_id,
                        name,
                        str(u.get("role") or "supporting"),
                        str(u.get("personality") or ""),
                        str(u.get("goals") or ""),
                        json.dumps(
                            {
                                "current_state": u.get("current_state") or "",
                                "last_weekly_change": change_log,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
            if not change_log:
                continue
            dup = conn.execute(
                "SELECT id FROM character_evolution WHERE novel_id=? AND name=? "
                "AND change_log=? LIMIT 1",
                (novel_id, name, change_log),
            ).fetchone()
            if dup is None:
                conn.execute(
                    "INSERT INTO character_evolution(novel_id,chapter_id,name,snapshot,"
                    "change_log,arc,created_at) VALUES(?,0,?,?,?,?,datetime('now','localtime'))",
                    (
                        novel_id,
                        name,
                        json.dumps(u, ensure_ascii=False),
                        change_log,
                        str(u.get("arc") or ""),
                    ),
                )
                updated += 1
        conn.commit()
        return {"ok": True, "updated": updated}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"persist_character_updates failed: {str(exc)[:200]}"}


def clean_character_evolution(conn, novel_id=0, keep=200):
    """Keep the newest `keep` evolution rows per novel; older rows are pruned."""
    keep = max(1, int(keep or 200))
    sql = (
        "DELETE FROM character_evolution WHERE id IN ("
        "  SELECT id FROM ("
        "    SELECT id, ROW_NUMBER() OVER (PARTITION BY novel_id ORDER BY id DESC) rn "
        "    FROM character_evolution"
    )
    params = []
    if novel_id:
        sql += " WHERE novel_id=?"
        params.append(int(novel_id))
    sql += "  ) WHERE rn > ?"
    params.append(keep)
    sql += ")"
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return {"ok": True, "removed": cur.rowcount}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"clean_character_evolution failed: {str(exc)[:200]}"}


def apply_report(conn, novel_id, report):
    """Persist a meeting report: blueprints, reader persona, volume goal."""
    decisions = report.get("decisions") or {}
    cover_prompt = str(report.get("cover_prompt") or "").strip()
    row = conn.execute(
        "SELECT id, outline, volume_goal, cover_prompt, status FROM novels WHERE id=?", (novel_id,)
    ).fetchone()
    if row is None:
        return {"ok": False, "error": "no novel"}
    outline = json.loads(row["outline"] or "{}")
    outline["blueprints"] = merge_blueprints(
        outline.get("blueprints") or [], decisions.get("blueprint_updates") or []
    )
    persona = decisions.get("reader_persona")
    if isinstance(persona, dict) and persona.get("preference"):
        bible = outline.get("bible") or {}
        bible["reader_persona"] = persona
        outline["bible"] = bible
    char_updates = decisions.get("character_updates")
    if isinstance(char_updates, list) and char_updates:
        bible = outline.get("bible") or {}
        chars = bible.get("characters") or []
        by_name = {c.get("name"): c for c in chars}
        for u in char_updates:
            name = str(u.get("name") or "")
            if not name:
                continue
            target = by_name.get(name)
            if target is None:
                target = {"name": name, "role": "supporting"}
                chars.append(target)
                by_name[name] = target
            for k in ("personality", "current_state", "goals", "speech_style"):
                if u.get(k):
                    target[k] = str(u[k])
        bible["characters"] = chars
        outline["bible"] = bible
        persist_character_updates(conn, novel_id, char_updates)
        clean_character_evolution(conn, novel_id)
    goal = decisions.get("volume_goal_adjust")
    if goal:
        outline["volume_goal"] = str(goal)
    finish = decisions.get("finish_decision") or {}
    finish_note = ""
    if finish.get("should_finish") and row["status"] not in ("finished",):
        conn.execute(
            "UPDATE novels SET status='finishing', finish_remaining=?, finish_note=? WHERE id=?",
            (
                int(finish.get("remaining_chapters") or 0),
                json.dumps(finish.get("reasons") or [], ensure_ascii=False),
                novel_id,
            ),
        )
        finish_note = "finishing"
    next_book = decisions.get("next_book")
    created_next = False
    if isinstance(next_book, dict) and next_book.get("book_name") and row["status"] == "finished":
        dup = conn.execute(
            "SELECT id FROM novels WHERE title=? AND status='planning'",
            (str(next_book["book_name"]),),
        ).fetchone()
        if dup is None:
            existing = conn.execute(
                "SELECT id FROM novels WHERE status='planning' LIMIT 1"
            ).fetchone()
            if existing is None:
                protagonists = json.dumps(
                    [{"name": str(next_book.get("protagonist") or "主角"), "role": "主角"}],
                    ensure_ascii=False,
                )
                conn.execute(
                    "INSERT INTO novels(title,genre,premise,selling_point,platform,status,abstract,protagonists,cover_prompt,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                    (
                        str(next_book["book_name"])[:50],
                        str(next_book.get("genre") or "都市"),
                        str(next_book.get("abstract") or ""),
                        str(next_book.get("selling_point") or ""),
                        "fanqie",
                        "planning",
                        str(next_book.get("abstract") or ""),
                        protagonists,
                        cover_prompt,
                    ),
                )
                created_next = True
    cover_prompt = cover_prompt or str(row["cover_prompt"] or "")
    conn.execute(
        "UPDATE novels SET outline=?, volume_goal=?, cover_prompt=?, updated_at=? WHERE id=?",
        (
            json.dumps(outline, ensure_ascii=False),
            str(goal or row["volume_goal"] or ""),
            cover_prompt,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            novel_id,
        ),
    )
    conn.commit()
    result = {
        "ok": True,
        "blueprints": len(outline["blueprints"]),
        "reader_persona": bool(persona),
        "volume_goal": str(goal or ""),
        "finish": finish_note,
        "next_book_created": created_next,
        "cover_prompt": bool(cover_prompt),
    }
    if char_updates:
        result["character_updates"] = len(char_updates)
    audit.log(
        conn,
        "meeting",
        "apply_report",
        target_type="novel",
        target_id=novel_id,
        detail={
            "blueprints": result["blueprints"],
            "finish": finish_note,
            "next_book_created": created_next,
        },
        source="meeting",
    )
    return result


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="落盘架构师周会结果")
    ap.add_argument("payload_b64", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--db", default="demo.db")
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            payload = json.load(f)
    elif args.payload_b64:
        payload = json.loads(base64.b64decode(args.payload_b64).decode("utf-8"))
    else:
        raise SystemExit("usage: apply_architect.py <base64-json> | --file <json-file>")
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        book_id = str(payload.get("book_id") or "")
        row = None
        if book_id:
            row = conn.execute(
                "SELECT id, outline, volume_goal, cover_prompt FROM novels "
                "WHERE book_id=? ORDER BY id DESC LIMIT 1",
                (book_id,),
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, outline, volume_goal, cover_prompt FROM novels ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            print(json.dumps({"ok": False, "error": "no novel"}, ensure_ascii=False))
            return

        outline = json.loads(row["outline"] or "{}")
        outline["blueprints"] = merge_blueprints(
            outline.get("blueprints") or [], payload.get("blueprint_updates") or []
        )
        bible = outline.get("bible") or {}
        if payload.get("reader_persona") and isinstance(payload["reader_persona"], dict):
            bible["reader_persona"] = payload["reader_persona"]
        outline["bible"] = bible
        if payload.get("volume_goal"):
            outline["volume_goal"] = str(payload["volume_goal"])

        cover_prompt = (
            str(payload.get("cover_prompt") or "").strip()
            or str(row["cover_prompt"] or "")
        )
        conn.execute(
            "UPDATE novels SET outline=?, volume_goal=?, cover_prompt=?, updated_at=? WHERE id=?",
            (
                json.dumps(outline, ensure_ascii=False),
                str(payload.get("volume_goal") or row["volume_goal"] or ""),
                cover_prompt,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                row["id"],
            ),
        )
        conn.commit()
        print(
            json.dumps(
                {
                    "ok": True,
                    "blueprints": len(outline["blueprints"]),
                    "reader_persona": bool(bible.get("reader_persona")),
                    "cover_prompt": bool(cover_prompt),
                },
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
