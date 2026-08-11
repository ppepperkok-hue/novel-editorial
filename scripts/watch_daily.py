"""Watch the running daily scheduler via local daily_runs + DB (de-n8n)."""

import sys
import time
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = str(ROOT / "demo.db")

def snapshot():
    from novel_pipeline import db as pipeline_db

    pconn = pipeline_db.connect(DB)
    try:
        row = pconn.execute(
            "SELECT run_id, status, started_at, finished_at FROM daily_runs "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        latest = dict(row) if row else {}
        latest["id"] = latest.get("run_id")
    finally:
        pconn.close()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        novels = [
            dict(r)
            for r in conn.execute(
                "SELECT id, title, status, book_id FROM novels ORDER BY id"
            ).fetchall()
        ]
        chapters = [
            dict(r)
            for r in conn.execute(
                "SELECT seq, title, status, words, published_at FROM chapters ORDER BY seq"
            ).fetchall()
        ]
        publishes = [
            dict(r)
            for r in conn.execute(
                "SELECT chapter_id, result, error, created_at FROM publish_logs "
                "ORDER BY id DESC LIMIT 5"
            ).fetchall()
        ]
        costs = conn.execute(
            "SELECT ROUND(SUM(cost),4) c FROM cost_logs WHERE created_at>=date('now','localtime','-1 day')"
        ).fetchone()["c"]
    finally:
        conn.close()
    return {
        "exec": latest,
        "novels": novels,
        "chapters": chapters,
        "publishes": publishes,
        "cost_today": costs,
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    for _ in range(90):
        s = snapshot()
        print(
            f"[{time.strftime('%H:%M:%S')}] exec={s['exec']['id']} "
            f"status={s['exec']['status']} chapters={len(s['chapters'])} "
            f"publishes={len(s['publishes'])} cost={s['cost_today']}"
        )
        for c in s["chapters"][-3:]:
            print(
                f"  ch{c['seq']} {c['title']} {c['status']} "
                f"words={c['words']} pub={c['published_at'] or '-'}"
            )
        for p in s["publishes"][-3:]:
            print(f"  pub ch{p['chapter_id']} {p['result']} err={p['error'] or '-'}")
        if s["exec"].get("status") in ("completed", "partial", "failed", "error", "running"):
            print("EXEC DONE:", s["exec"]["status"])
            if s["exec"]["status"] != "running":
                break
        time.sleep(30)


if __name__ == "__main__":
    main()
