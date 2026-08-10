"""Resolve the active novel (book_id/volume_id) from the local database.

The n8n workflow previously read FANQIE_BOOK_ID from its process environment,
which does not refresh when bind_book/create_book updates ~/.n8n/.env.
Reading from the database keeps the running workflow in sync without an
n8n restart.
"""

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
    ap = argparse.ArgumentParser(description="读取当前活跃作品")
    ap.add_argument("--db", default=str(ROOT / "demo.db"))
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    try:
        row = conn.execute(
            "SELECT book_id, volume_id FROM novels "
            "WHERE status IN ('publishing','finishing') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        print(
            json.dumps(
                {
                    "book_id": row["book_id"] if row else "",
                    "volume_id": row["volume_id"] if row else "",
                },
                ensure_ascii=False,
            )
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
