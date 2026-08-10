"""Regression tests for the third review round (A/B fixes)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402


def make_db(status="publishing"):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,book_id) VALUES('书','都市','设定',?,'b1')",
        (status,),
    )
    conn.execute("INSERT INTO volumes(novel_id,seq,goal) VALUES(1,1,'第一卷')")
    conn.commit()
    conn.close()
    return path


class MigrationDedupTests(unittest.TestCase):
    def test_dedup_keeps_published_row_and_cleans_children(self):
        path = make_db()
        # Insert duplicate (novel_id=1, seq=1): draft first, published later.
        conn = db.connect(path)
        conn.execute("DROP INDEX IF EXISTS idx_chapters_novel_seq_unique")
        conn.execute(
            "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
            "VALUES(1,1,1,'draft章纲','draft','第 1 章')"
        )
        conn.execute(
            "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title,published_at) "
            "VALUES(1,1,1,'pub章纲','published','第 1 章','2026-08-10 10:00:00')"
        )
        conn.execute(
            "INSERT INTO publish_logs(chapter_id,platform,action,result,ai_declared,created_at) "
            "VALUES(2,'fanqie','publish','success',1,datetime('now','localtime'))"
        )
        conn.commit()
        conn.close()

        conn = db.connect(path)
        db._migrate(conn)  # simulate the startup migration pass
        try:
            rows = conn.execute(
                "SELECT id, status FROM chapters WHERE novel_id=1 AND seq=1"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "published")
            self.assertEqual(rows[0]["id"], 2)
            orphans = conn.execute(
                "SELECT COUNT(*) c FROM publish_logs WHERE chapter_id NOT IN "
                "(SELECT id FROM chapters)"
            ).fetchone()["c"]
            self.assertEqual(orphans, 0)
        finally:
            conn.close()


class AdapterLoggingTests(unittest.TestCase):
    def test_success_writes_publish_log(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
                "VALUES(1,1,1,'章纲','reviewed','第 1 章')"
            )
            conn.execute(
                "INSERT INTO chapter_content(chapter_id,content,updated_at) "
                "VALUES(1,'正文内容',datetime('now','localtime'))"
            )
            conn.commit()
            from novel_pipeline.publisher import FanqieHttpAdapter

            adapter = FanqieHttpAdapter(conn)
            with mock.patch("tools.publish_stock.publish_chapter", return_value=(True, "i1", "")):
                with mock.patch("tools.publish_stock.load_env", return_value={"FANQIE_COOKIE": "c"}):
                    result = adapter.publish(1, "正文内容")
            self.assertEqual(result["item_id"], "i1")
            log = conn.execute(
                "SELECT result FROM publish_logs WHERE chapter_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(log["result"], "success")
        finally:
            conn.close()

    def test_failure_writes_failed_log(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
                "VALUES(1,1,1,'章纲','reviewed','第 1 章')"
            )
            conn.execute(
                "INSERT INTO chapter_content(chapter_id,content,updated_at) "
                "VALUES(1,'正文内容',datetime('now','localtime'))"
            )
            conn.commit()
            from novel_pipeline.publisher import FanqieHttpAdapter

            adapter = FanqieHttpAdapter(conn)
            with mock.patch(
                "tools.publish_stock.publish_chapter",
                return_value=(False, None, "章节字数不足"),
            ):
                with mock.patch("tools.publish_stock.load_env", return_value={"FANQIE_COOKIE": "c"}):
                    with self.assertRaises(RuntimeError):
                        adapter.publish(1, "正文内容")
            log = conn.execute(
                "SELECT result, error FROM publish_logs WHERE chapter_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(log["result"], "failed")
            self.assertIn("章节字数不足", log["error"])
        finally:
            conn.close()


class SchedulerMissingBodyTests(unittest.TestCase):
    def test_missing_body_skips_not_publishes_outline(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
                "VALUES(1,1,1,'章纲文本','reviewed','第 1 章')"
            )
            conn.commit()
            from novel_pipeline.publisher import ManualAdapter
            from novel_pipeline.scheduler import Scheduler

            class RecordingAdapter(ManualAdapter):
                def __init__(self):
                    self.sent = []

                def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
                    self.sent.append(text)
                    return {"result": "ok"}

            adapter = RecordingAdapter()
            report = Scheduler(adapter=adapter, chapters_per_day=2).tick(conn)
            self.assertEqual(adapter.sent, [], "outline must never be published as body")
            self.assertTrue(report["failures"])
            row = conn.execute("SELECT status FROM chapters WHERE id=1").fetchone()
            self.assertEqual(row["status"], "reviewed")
        finally:
            conn.close()


class WeeklyDiaryBriefTests(unittest.TestCase):
    def test_weekly_prompt_includes_agent_brief(self):
        path = make_db()
        conn = db.connect(path)
        try:
            from tools import write_diaries

            materials = {
                "agent_briefs": {"planner": {"blueprints_total": 7, "chapters_this_week": 2}}
            }
            with mock.patch("tools.write_diaries.chat_deepseek") as chat:
                chat.return_value = {
                    "text": json.dumps(
                        {"what_done": "x", "mood": {"satisfaction": 0.5}},
                        ensure_ascii=False,
                    ),
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    "model": "deepseek-v4-flash",
                }
                write_diaries.write(conn, 1, "weekly", dry_run=False, materials=materials)
            users = [c[0][2] for c in chat.call_args_list]
            self.assertTrue(
                any("blueprints_total" in u and "我的本周简报" in u for u in users),
                "at least one weekly diary prompt must carry its agent brief",
            )
        finally:
            conn.close()


class TokenGetTests(unittest.TestCase):
    def test_get_allowed_without_token(self):
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import urlopen

        from novel_pipeline.web_api import make_handler

        path = make_db()
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(path))
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        with mock.patch("novel_pipeline.web_api._panel_token", return_value="secret"):
            with urlopen(f"http://127.0.0.1:{port}/api/dashboard", timeout=10) as resp:
                self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
