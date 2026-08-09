"""SQLite 数据库备份：复制到 backups/，只保留最近 N 份。"""

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_KEEP = 3


def backup_db(db_path, backup_dir, keep=DEFAULT_KEEP):
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"{db_path.stem}_{stamp}.db"
    shutil.copy2(db_path, target)
    backups = sorted(backup_dir.glob(f"{db_path.stem}_*.db"))
    for old in backups[:-keep]:
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
    print(backup_db(args.db, args.backup_dir, args.keep))


if __name__ == "__main__":
    main()
