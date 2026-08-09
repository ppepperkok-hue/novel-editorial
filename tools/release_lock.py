"""Release the daily run lock (called at the end of the daily workflow)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    lock = ROOT / "n8n_tmp" / "daily.lock"
    try:
        lock.unlink()
        print("lock released")
    except OSError:
        print("no lock to release")


if __name__ == "__main__":
    sys.exit(main())
