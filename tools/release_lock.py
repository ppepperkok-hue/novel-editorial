"""Release the per-database daily run lock (end of the daily workflow)."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description="release the daily run lock")
    ap.add_argument("--db", default="demo.db")
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    lock = ROOT / "n8n_tmp" / f"{db_path.stem}.lock"
    try:
        lock.unlink()
        print("lock released")
    except OSError:
        print("no lock to release")


if __name__ == "__main__":
    sys.exit(main())
