"""Delete a Fanqie book and reset the local novel back to planning.

Endpoint (validated against the writer console, 2026-08-11):
    POST /api/author/book/delete/v0  body: book_id
Permission gate:
    GET /api/author/book/book_detail/v0/?book_id= -> data.can_delete

The platform only allows deletion when ``can_delete`` is true (books under
signing review cannot be deleted). Deleting is irreversible on Fanqie, so
the tool refuses to run without --yes and the panel sends confirm=true.

Run from the pipeline root:
    python tools/delete_book.py --novel-id N --yes
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402
from novel_pipeline.services import audit  # noqa: E402
from tools.create_book import http_json, load_env  # noqa: E402


def _book_detail(env, book_id):
    res = http_json(
        "GET",
        "/api/author/book/book_detail/v0/",
        {"book_id": book_id, "image_fmt_list": "160x214"},
        env,
    )
    if res.get("code") != 0:
        raise RuntimeError(f"book_detail: {res.get('message') or res}")
    return res.get("data") or {}


def delete_book_on_fanqie(conn, novel_id, confirm=False):
    """Delete the Fanqie book bound to a novel, then reset it to planning."""
    row = conn.execute(
        "SELECT id, title, status, book_id, volume_id FROM novels WHERE id=?",
        (novel_id,),
    ).fetchone()
    if row is None:
        return {"ok": False, "error": f"novel {novel_id} not found"}
    book_id = str(row["book_id"] or "").strip()
    if not book_id:
        return {"ok": False, "error": "本地未绑定番茄书籍，无需删除"}
    if not confirm:
        return {"ok": False, "error": "删除番茄书籍不可恢复，需要二次确认"}

    env = load_env()
    if not env.get("FANQIE_COOKIE"):
        return {"ok": False, "error": "缺少 FANQIE_COOKIE，请先配置番茄登录态"}

    try:
        detail = _book_detail(env, book_id)
        if not detail.get("can_delete"):
            reason = str(detail.get("cant_delete_reason") or "").strip()
            if detail.get("is_signing"):
                reason = reason or "作品签约中暂不支持删除"
            return {
                "ok": False,
                "error": f"番茄不允许删除：{reason or '未知原因'}",
            }
        res = http_json(
            "POST", "/api/author/book/delete/v0", {"book_id": book_id}, env
        )
    except (RuntimeError, ValueError) as exc:
        return {"ok": False, "error": f"删除请求失败：{exc}"}

    if res.get("code") != 0:
        return {"ok": False, "error": f"番茄拒绝删除：{res.get('message') or res}"}

    conn.execute(
        "UPDATE novels SET book_id='', volume_id='', status='planning' WHERE id=?",
        (novel_id,),
    )
    conn.commit()
    audit.log(
        conn,
        "ending",
        "delete_book",
        target_type="novel",
        target_id=novel_id,
        detail={"book_id": book_id},
    )
    return {
        "ok": True,
        "note": f"已在番茄删除《{row['title']}》并重置为待建书",
    }


def main():
    ap = argparse.ArgumentParser(description="Delete a Fanqie book and reset local novel")
    ap.add_argument("--db", default=str(config.DB_PATH))
    ap.add_argument("--novel-id", type=int, required=True)
    ap.add_argument("--yes", action="store_true", help="confirm the irreversible delete")
    args = ap.parse_args()
    conn = db.connect(Path(args.db))
    try:
        result = delete_book_on_fanqie(conn, args.novel_id, confirm=args.yes)
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
