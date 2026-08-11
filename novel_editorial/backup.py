"""SQLite 数据库备份：复制到 backups/，只保留最近 N 份。"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_KEEP = 3
ROOT = Path(__file__).resolve().parent.parent


def backup_db(db_path, backup_dir, keep=DEFAULT_KEEP):
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"{db_path.stem}_{stamp}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(target))
    try:
        # sqlite3 backup API produces a consistent snapshot even in WAL mode
        # (a plain file copy would miss -wal/-shm and yield a torn database).
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    backups = sorted(backup_dir.glob(f"{db_path.stem}_*.db"))
    stale = backups[:-keep] if keep > 0 else backups
    for old in stale:
        old.unlink()
    return str(target)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="数据库备份")
    ap.add_argument("--db", required=True, help="SQLite 数据库路径")
    ap.add_argument("--backup-dir", default="backups")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    backup_dir = Path(args.backup_dir)
    if not backup_dir.is_absolute():
        backup_dir = ROOT / backup_dir
    print(backup_db(db_path, backup_dir, args.keep))


if __name__ == "__main__":
    main()
