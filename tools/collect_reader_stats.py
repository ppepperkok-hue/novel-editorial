"""Fetch per-chapter read completion / follow rates from Fanqie author API.

Writes demo_data/reader_stats.csv in the format data_feedback expects:
chapter,finish_rate,follow_rate (0-1 floats; empty field = missing data,
so consumers must not treat it as a 0.0 rate).
"""

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from novel_editorial import config, db  # noqa: E402

OUT_CSV = config.READER_CSV
PAGE_SIZE = 200
MAX_PAGES = 100
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


def _trace(message):
    """Append a trace line to alerts.log; I/O failure must not crash the run."""
    try:
        with config.ALERTS_LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n")
    except OSError:
        pass


def load_env(env_file):
    """Load env vars from the given file (default ~/.n8n/.env) into
    os.environ without overwriting already-set process variables."""
    if env_file:
        env = dict(os.environ)
        path = Path(env_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip())
    else:
        env = config.load_env()
    for k, v in env.items():
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
    """Fetch every chapter-stats page (PAGE_SIZE per page) until a short page."""
    all_items = []
    for page in range(MAX_PAGES):
        qs = urllib.parse.urlencode(
            {
                "aid": "2503",
                "app_name": "muye_novel",
                "book_id": book_id,
                "page_index": str(page),
                "page_count": str(PAGE_SIZE),
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
            payload = json.loads(r.read().decode("utf-8", "ignore"))
        if payload.get("code") != 0:
            if not all_items:
                return payload
            raise RuntimeError(
                f"第 {page + 1} 页采集失败：{payload.get('message') or payload}"
            )
        items = (payload.get("data") or {}).get("chapter_stats_list") or []
        if not isinstance(items, list):
            _trace(
                f"collect_reader_stats: 第 {page + 1} 页 chapter_stats_list "
                f"({type(items).__name__}) 非 list，已跳过该页"
            )
            items = []
        all_items.extend(items)
        if len(items) < PAGE_SIZE:
            break
    else:
        _trace(
            f"collect_reader_stats: 达到页数上限 {MAX_PAGES}（每页 {PAGE_SIZE} 章），"
            "已截断，后续章节未采集"
        )
    return {"code": 0, "data": {"chapter_stats_list": all_items}}


def run(db_path, env_file=None, out_csv=None):
    """Collect per-chapter reader stats into the CSV consumed by data_feedback.

    Library entry shared by the CLI and the Python scheduler.
    The active book comes from the DB (current_book semantics); the
    FANQIE_BOOK_ID env var is only a fallback for legacy n8n paths.
    """
    if env_file:
        load_env(env_file)
    conn = db.connect(db_path)
    try:
        active = conn.execute(
            "SELECT book_id FROM novels "
            "WHERE status IN ('publishing','finishing') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    book_id = str(active["book_id"] or "") if active else ""
    if not book_id:
        book_id = os.environ.get("FANQIE_BOOK_ID", "")
    if not book_id:
        return {
            "ok": False,
            "error": "没有活跃连载作品（publishing/finishing），且未设置 FANQIE_BOOK_ID",
        }
    try:
        payload = fetch_stats(book_id)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    if payload.get("code") != 0:
        return {
            "ok": False,
            "error": str(payload.get("message") or payload)[:200],
        }

    conn = db.connect(db_path)
    item_to_seq = {}
    for r in conn.execute(
        "SELECT seq, fanqie_item_id FROM chapters WHERE fanqie_item_id != ''"
    ):
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
                "finish_rate": finish if finish is not None else "",
                "follow_rate": follow if follow is not None else "",
            }
        )

    target = Path(out_csv) if out_csv else OUT_CSV
    if not rows:
        if target.exists():
            return {
                "ok": True,
                "chapters": 0,
                "file": str(target),
                "warning": "无匹配章节，保留原 reader_stats.csv 未覆盖",
            }
        return {
            "ok": False,
            "error": "无匹配章节，未创建空表",
            "chapters": 0,
            "file": str(target),
        }
    target.parent.mkdir(exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["chapter", "finish_rate", "follow_rate"])
        w.writeheader()
        w.writerows(rows)
    return {"ok": True, "chapters": len(rows), "file": str(target)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="采集番茄章节完读率/追读率")
    ap.add_argument("--db", default="demo.db")
    ap.add_argument("--env-file", default=str(config.N8N_ENV_FILE))
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    print(json.dumps(run(db_path, env_file=args.env_file), ensure_ascii=False))


if __name__ == "__main__":
    main()
