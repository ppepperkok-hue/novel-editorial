"""Check the chapter stock pool and the publish target for the current run."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="检查存稿池与本次发布目标")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        settings = {
            r["key"]: r["value"]
            for r in conn.execute("SELECT key, value FROM settings").fetchall()
        }
        stock = conn.execute(
            "SELECT COUNT(*) c FROM chapters WHERE status='reviewed'"
        ).fetchone()["c"]
        target = int(settings.get("pending_publish") or 0) or int(
            settings.get("daily_chapters") or 2
        )
        target = max(1, min(target, 10))
        need = max(0, target - stock)
        print(
            json.dumps(
                {
                    "stock": stock,
                    "target": target,
                    "need": need,
                    "novel_premise": settings.get("novel_premise", ""),
                    "novel_keywords": settings.get("novel_keywords", ""),
                    "novel_genre": settings.get("novel_genre", ""),
                },
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
