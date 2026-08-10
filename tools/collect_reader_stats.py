"""Fetch per-chapter read completion / follow rates from Fanqie author API.

Writes demo_data/reader_stats.csv in the format data_feedback expects:
chapter,finish_rate,follow_rate (0-1 floats).
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_pipeline import config, db  # noqa: E402

OUT_CSV = ROOT / "demo_data" / "reader_stats.csv"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def load_env(env_file):
    for k, v in config.load_env().items():
        os.environ.setdefault(k, v)


def norm_rate(value):
    """Accept '', '12.3', '12.3%', 0.123 -> float 0-1 or None."""
    if value is None:
        return None
    s = str(value).strip().strip("%")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v > 1:
        v = v / 100.0
    return round(v, 6)


def fetch_stats(book_id):
    qs = urllib.parse.urlencode(
        {
            "aid": "2503",
            "app_name": "muye_novel",
            "book_id": book_id,
            "page_index": "0",
            "page_count": "200",
        }
    )
    req = urllib.request.Request(
        "https://fanqienovel.com/api/author/stats/chapter_list_v1/v0/?" + qs,
        headers={
            "Cookie": os.environ["FANQIE_COOKIE"],
            "X-Secsdk-Csrf-Token": os.environ["FANQIE_CSRF_TOKEN"],
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://fanqienovel.com",
            "Referer": "https://fanqienovel.com/main/writer/",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="采集番茄章节完读率/追读率")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--env-file", default=str(ENV_FILE))
    args = ap.parse_args()

    load_env(args.env_file)
    book_id = os.environ.get("FANQIE_BOOK_ID", "")
    try:
        payload = fetch_stats(book_id)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)[:200]}, ensure_ascii=False))
        return 0
    if payload.get("code") != 0:
        print(json.dumps({"ok": False, "error": str(payload.get("message") or payload)[:200]}, ensure_ascii=False))
        return 0

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    conn = db.connect(db_path)
    item_to_seq = {}
    for r in conn.execute("SELECT seq, fanqie_item_id FROM chapters WHERE fanqie_item_id != ''"):
        item_to_seq[str(r["fanqie_item_id"])] = r["seq"]
    conn.close()

    rows = []
    for item in (payload.get("data") or {}).get("chapter_stats_list") or []:
        seq = item_to_seq.get(str(item.get("item_id") or ""))
        if not seq:
            continue
        finish = norm_rate(item.get("read_completion_rate"))
        follow = norm_rate(item.get("follow_read_rate"))
        if finish is None and follow is None:
            continue
        rows.append(
            {
                "chapter": seq,
                "finish_rate": finish if finish is not None else 0.0,
                "follow_rate": follow if follow is not None else 0.0,
            }
        )

    OUT_CSV.parent.mkdir(exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["chapter", "finish_rate", "follow_rate"])
        w.writeheader()
        w.writerows(rows)

    print(
        json.dumps(
            {"ok": True, "chapters": len(rows), "file": str(OUT_CSV)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
