"""Release the per-database daily run lock (end of the daily workflow)."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.preflight import _pid_alive  # noqa: E402


def _read_owner(lock):
    """Return (pid, task) recorded in the lock file.

    Handles both the plain "PID timestamp" format written by
    tools/preflight.acquire_lock and a JSON {"pid": ..., "task": ...} record.
    """
    try:
        content = lock.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None, None
    if not content:
        return None, None
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            pid = data.get("pid")
            task = data.get("task")
            try:
                return int(pid), str(task) if task else None
            except (TypeError, ValueError):
                return None, None
    except (TypeError, ValueError):
        pass
    parts = content.split()
    if not parts:
        return None, None
    try:
        return int(parts[0]), None
    except ValueError:
        return None, None


def main():
    ap = argparse.ArgumentParser(description="release the daily run lock")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument(
        "--task",
        default=None,
        help="expected lock task name (verified when the lock records one)",
    )
    args = ap.parse_args()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    lock = ROOT / "n8n_tmp" / f"{db_path.stem}.lock"
    if not lock.exists():
        print("no lock to release")
        return 0
    pid, task = _read_owner(lock)
    if pid is None:
        print("lock release refused: cannot read lock owner")
        return 1
    if args.task and task is not None and task != args.task:
        print(
            f"lock release refused: lock task {task!r} does not match "
            f"{args.task!r}"
        )
        return 1
    if pid != os.getpid() and _pid_alive(pid):
        print(f"lock release refused: lock held by live process {pid}")
        return 1
    try:
        lock.unlink()
    except FileNotFoundError:
        print("no lock to release")
        return 0
    except OSError as e:
        print(f"lock release failed: {e}")
        return 1
    if pid != os.getpid():
        print(f"lock released (stale owner {pid} no longer running)")
    else:
        print("lock released")
    return 0


if __name__ == "__main__":
    sys.exit(main())
