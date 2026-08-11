"""R4-1: workday reminders - unopened office, opened but unpublished,
awaiting-close decision. Each reason fires at most once per day.

The popup is a hidden PowerShell WinForms MessageBox so the user gets a real
desktop notification without a console window. No reminders while the office
has already closed for the day.
"""

from __future__ import annotations

import base64
import json
import subprocess
import threading
import time
from datetime import datetime

from novel_editorial import db
from tools.app_settings import get_all, set_many

_KINDS = ("unopened", "unpublished", "awaiting")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _popup(message):
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "[System.Windows.Forms.MessageBox]::Show('"
        + str(message).replace("'", "''")
        + "', '文学编辑部')"
    )
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        subprocess.Popen(
            [
                "powershell",
                "-WindowStyle",
                "Hidden",
                "-NoProfile",
                "-EncodedCommand",
                encoded,
            ]
        )
    except OSError:
        pass


def _last_marks(conn):
    settings = get_all(conn)
    raw = settings.get("reminder_last", "{}")
    try:
        data = json.loads(raw or "{}")
    except (TypeError, ValueError):
        data = {}
    if data.get("date") != _today():
        data = {"date": _today(), "kinds": []}
    return data


def _mark(conn, kind):
    data = _last_marks(conn)
    if kind not in data["kinds"]:
        data["kinds"].append(kind)
    set_many(conn, {"reminder_last": json.dumps(data, ensure_ascii=False)})


def check_and_notify(conn):
    """Check today's workday state and fire at most one popup per reason."""
    marks = _last_marks(conn)
    today = _today()
    opened = conn.execute(
        "SELECT COUNT(*) c FROM daily_runs "
        "WHERE source='workday' AND substr(started_at,1,10)=?",
        (today,),
    ).fetchone()["c"]
    published = conn.execute(
        "SELECT COUNT(*) c FROM publish_logs "
        "WHERE result='success' AND substr(created_at,1,10)=?",
        (today,),
    ).fetchone()["c"]
    row = conn.execute(
        "SELECT phase, status FROM daily_runs "
        "WHERE source='workday' ORDER BY id DESC LIMIT 1"
    ).fetchone()

    fired = []
    if opened == 0:
        if "unopened" not in marks["kinds"]:
            _popup("编辑部今天还没开工，记得去面板点开工")
            _mark(conn, "unopened")
            fired.append("unopened")
    elif (
        published == 0
        and row
        and row["status"] == "running"
        and row["phase"] != "awaiting_close"
    ):
        if "unpublished" not in marks["kinds"]:
            _popup("编辑部今天开工了，但还没有发稿")
            _mark(conn, "unpublished")
            fired.append("unpublished")
    if row and row["phase"] == "awaiting_close":
        if "awaiting" not in marks["kinds"]:
            _popup("今天的工作完成了，可以收工、开会或继续补跑")
            _mark(conn, "awaiting")
            fired.append("awaiting")
    return {"ok": True, "fired": fired, "opened": opened, "published": published}


def start_worker(db_path, delay_seconds=60, interval_seconds=1800):
    """Start the reminder daemon thread: one check after startup, then near
    `reminder_time` every interval. Never blocks the API server."""
    def worker():
        time.sleep(delay_seconds)
        try:
            conn = db.connect(db_path)
            try:
                check_and_notify(conn)
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            print("reminder check failed:", str(exc)[:200])
        while True:
            time.sleep(interval_seconds)
            try:
                conn = db.connect(db_path)
                try:
                    settings = get_all(conn)
                    rt = str(settings.get("reminder_time", "20:00")).split(":")
                    now = datetime.now()
                    if (
                        len(rt) == 2
                        and now.hour == int(rt[0])
                        and now.minute == int(rt[1])
                    ):
                        check_and_notify(conn)
                finally:
                    conn.close()
            except Exception as exc:  # noqa: BLE001
                print("reminder loop failed:", str(exc)[:200])

    threading.Thread(target=worker, daemon=True).start()
