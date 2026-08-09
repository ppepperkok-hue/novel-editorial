"""Read/write pipeline settings stored in SQLite.

Settings are consumed by preflight (daily_enabled, monthly_budget),
get_meta (target_words, style_tweak) and the web control panel.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import db  # noqa: E402

DEFAULTS = {
    "daily_enabled": "true",
    "monthly_budget": "100",
    "target_words": "2000",
    "style_tweak": "",
    "daily_run_time": "08:00",
}


def connect(db_path):
    p = Path(db_path)
    if not p.is_absolute():
        p = ROOT / p
    return db.connect(p)


def ensure_defaults(conn):
    for k, v in DEFAULTS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v)
        )
    conn.commit()


def get_all(conn):
    ensure_defaults(conn)
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_bool(conn, key, default=False):
    v = get_all(conn).get(key, "true" if default else "false")
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def get_float(conn, key, default=0.0):
    try:
        return float(get_all(conn).get(key, default))
    except (TypeError, ValueError):
        return default


def get_int(conn, key, default=0):
    try:
        return int(float(get_all(conn).get(key, default)))
    except (TypeError, ValueError):
        return default


def set_many(conn, values):
    ensure_defaults(conn)
    for k, v in values.items():
        conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (k, str(v)),
        )
    conn.commit()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="流水线设置读写")
    ap.add_argument("--db", default="demo.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("get")
    setp = sub.add_parser("set")
    setp.add_argument("--key", required=True)
    setp.add_argument("--value", required=True)
    args = ap.parse_args()

    conn = connect(args.db)
    try:
        if args.cmd == "get":
            print(json.dumps(get_all(conn), ensure_ascii=False))
        else:
            set_many(conn, {args.key: args.value})
            print(json.dumps({"ok": True, "key": args.key, "value": args.value}, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
