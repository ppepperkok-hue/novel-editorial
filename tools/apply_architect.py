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
        "SELECT id, outline, volume_goal FROM novels WHERE id=?", (novel_id,)
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
    goal = decisions.get("volume_goal_adjust")
    if goal:
        outline["volume_goal"] = str(goal)
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
    return {
        "ok": True,
        "blueprints": len(outline["blueprints"]),
        "reader_persona": bool(persona),
        "volume_goal": str(goal or ""),
    }


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
