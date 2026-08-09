"""Apply the weekly architect output back into the novel outline."""

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402
from novel_pipeline.services import audit  # noqa: E402


def merge_blueprints(old, updates):
    by_seq = {int(b.get("seq") or 0): b for b in old if b.get("seq")}
    for u in updates or []:
        seq = int(u.get("seq") or 0)
        if not seq:
            continue
        by_seq[seq] = {**by_seq.get(seq, {}), **u}
    return [by_seq[k] for k in sorted(by_seq)]


def apply_report(conn, novel_id, report):
    """Persist a meeting report: blueprints, reader persona, volume goal."""
    decisions = report.get("decisions") or {}
    row = conn.execute(
        "SELECT id, outline, volume_goal, status FROM novels WHERE id=?", (novel_id,)
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
            protagonists = json.dumps(
                [{"name": str(next_book.get("protagonist") or "主角"), "role": "主角"}],
                ensure_ascii=False,
            )
            conn.execute(
                "INSERT INTO novels(title,genre,premise,selling_point,platform,status,abstract,protagonists,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                (
                    str(next_book["book_name"])[:50],
                    str(next_book.get("genre") or "都市"),
                    str(next_book.get("abstract") or ""),
                    str(next_book.get("selling_point") or ""),
                    "fanqie",
                    "planning",
                    str(next_book.get("abstract") or ""),
                    protagonists,
                ),
            )
            created_next = True
    conn.execute(
        "UPDATE novels SET outline=?, volume_goal=?, updated_at=? WHERE id=?",
        (
            json.dumps(outline, ensure_ascii=False),
            str(goal or row["volume_goal"] or ""),
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
                "SELECT id, outline, volume_goal FROM novels "
                "WHERE book_id=? ORDER BY id DESC LIMIT 1",
                (book_id,),
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id, outline, volume_goal FROM novels ORDER BY id DESC LIMIT 1"
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

        conn.execute(
            "UPDATE novels SET outline=?, volume_goal=?, updated_at=? WHERE id=?",
            (
                json.dumps(outline, ensure_ascii=False),
                str(payload.get("volume_goal") or row["volume_goal"] or ""),
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
                },
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
