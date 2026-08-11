"""Check the chapter stock pool and the publish target for the current run."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import db  # noqa: E402


def check_stock(conn, novel_id=0):
    """Inspect the chapter stock pool and the publish target for the current run.

    Mirrors the n8n `查存稿` node: reads the active book from the database and
    the pending/daily chapter target from settings. When `novel_id` is given,
    stock and metadata are scoped to that novel only (multi-book isolation);
    otherwise the default scope is the newest active (publishing/finishing)
    novel, matching publish_stock's publish range rather than the whole library.
    """
    settings = {
        r["key"]: r["value"]
        for r in conn.execute("SELECT key, value FROM settings").fetchall()
    }
    if novel_id:
        book = conn.execute(
            "SELECT id, book_id, title, genre, premise, tags FROM novels WHERE id=?",
            (int(novel_id),),
        ).fetchone()
    else:
        book = conn.execute(
            "SELECT id, book_id, title, genre, premise, tags FROM novels "
            "WHERE status IN ('publishing','finishing') ORDER BY id DESC LIMIT 1"
        ).fetchone()
    stock_sql = "SELECT COUNT(*) c FROM chapters WHERE status='reviewed'"
    params = ()
    if novel_id:
        stock_sql += " AND novel_id=?"
        params = (int(novel_id),)
    elif book:
        stock_sql += " AND novel_id=?"
        params = (book["id"],)
    stock = conn.execute(stock_sql, params).fetchone()["c"]
    def _parse_int(raw, fallback):
        if raw in (None, ""):
            return fallback
        try:
            return int(raw)
        except (TypeError, ValueError):
            return fallback

    pending = _parse_int(settings.get("pending_publish"), 0)
    target = pending if pending else _parse_int(settings.get("daily_chapters"), 2)
    target = min(max(target, 0), 10)
    need = max(0, target - stock)
    book_id = str(book["book_id"] or "") if book else ""
    premise = str(book["premise"] or "").strip() if book else ""
    genre = str(book["genre"] or "").strip() if book else ""
    keywords = ""
    if book and book["tags"]:
        try:
            tags = json.loads(book["tags"])
            keywords = ",".join(str(t) for t in tags if t)
        except (TypeError, ValueError):
            keywords = str(book["tags"] or "")
    if not premise:
        premise = settings.get("novel_premise", "")
    if not genre:
        genre = settings.get("novel_genre", "")
    if not keywords:
        keywords = settings.get("novel_keywords", "")
    return {
        "scope": "novel" if novel_id else ("active_book" if book else "none"),
        "stock": stock,
        "target": target,
        "need": need,
        "novel_id": int(book["id"]) if book else 0,
        "book_id": book_id,
        "book_name": str(book["title"] or "").strip() if book else "",
        "novel_premise": premise,
        "novel_keywords": keywords,
        "novel_genre": genre,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="检查存稿池与本次发布目标")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    ap.add_argument("--novel-id", type=int, default=0)
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        print(
            json.dumps(
                check_stock(conn, novel_id=args.novel_id or None),
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
