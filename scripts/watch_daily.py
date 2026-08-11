"""Watch the running daily workflow via n8n executions + local DB."""

import json
import sys
import time
import urllib.request
import sqlite3
from pathlib import Path

DB = r"E:\code\novel-pipeline\demo.db"
KEY = "n8n_api_52e390a21bfb0d6620fe75ea343774df"


def n8n_get(path):
    req = urllib.request.Request(
        "http://127.0.0.1:5678/api/v1" + path,
        headers={"X-N8N-API-KEY": KEY},
        method="GET",
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8"))


def n8n_exec():
    conn = sqlite3.connect(Path.home() / ".n8n" / "database.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute(
            "SELECT id, status, startedAt, stoppedAt FROM execution_entity "
            "WHERE workflowId='SkLUnm3uRyBSY84F' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(r) if r else {}
    finally:
        conn.close()


def snapshot():
    latest = n8n_exec()
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
        if s["exec"].get("status") in ("success", "error", "crashed", "failed"):
            print("EXEC DONE:", s["exec"]["status"])
            break
        time.sleep(30)


if __name__ == "__main__":
    main()
