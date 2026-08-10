"""Tests for tools/publish_stock.py (three-step Fanqie publish chain)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from tools import publish_stock  # noqa: E402


def make_db(book_id="b1", volume_id="v1", status="ready"):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,book_id,volume_id) "
        "VALUES('测试书','玄幻','测试',?,?,?)",
        (status, book_id, volume_id),
    )
    conn.execute(
        "INSERT INTO volumes(novel_id,seq,goal) VALUES(1,1,'第一卷')"
    )
    conn.execute(
        "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
        "VALUES(1,1,1,'章纲','reviewed','第 1 章 开局')"
    )
    conn.execute(
        "INSERT INTO chapter_content(chapter_id,content,updated_at) "
        "VALUES(1,'第一段正文。第二段正文。',datetime('now','localtime'))"
    )
    conn.commit()
    conn.close()
    return path


class PublishStockTests(unittest.TestCase):
    def _run_main(self, path, env, responses):
        with mock.patch.object(sys, "argv", ["publish_stock", "--db", path]):
            with mock.patch("tools.publish_stock.load_env", return_value=env):
                with mock.patch("tools.publish_stock.http_form", side_effect=responses):
                    return publish_stock.main()

    def test_publish_success_marks_published_and_logs(self):
        path = make_db()
        env = {"FANQIE_COOKIE": "c", "FANQIE_CSRF_TOKEN": "t", "FANQIE_BOOK_ID": "b1"}
        responses = [
            {"code": 0, "data": {"item_id": "i1", "volume_id": "v1",
                                 "volume_data": [{"volume_id": "v1", "volume_name": "正文"}]}},
            {"code": 0, "data": {}},
            {"code": 0, "data": {}},
        ]
        conn = db.connect(path)
        try:
            self._run_main(path, env, responses)
            row = conn.execute("SELECT status, fanqie_item_id FROM chapters WHERE id=1").fetchone()
            self.assertEqual(row["status"], "published")
            self.assertEqual(row["fanqie_item_id"], "i1")
            log = conn.execute(
                "SELECT result FROM publish_logs WHERE chapter_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(log["result"], "success")
        finally:
            conn.close()

    def test_publish_reports_platform_error(self):
        path = make_db()
        env = {"FANQIE_COOKIE": "c", "FANQIE_CSRF_TOKEN": "t", "FANQIE_BOOK_ID": "b1"}
        conn = db.connect(path)
        try:
            self._run_main(
                path, env,
                [{"code": 1, "message": "章节字数不足"}] * 3,
            )
            row = conn.execute("SELECT status FROM chapters WHERE id=1").fetchone()
            self.assertEqual(row["status"], "reviewed", "failed publish must keep the chapter in stock")
            log = conn.execute(
                "SELECT result, error FROM publish_logs WHERE chapter_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(log["result"], "failed")
            self.assertIn("章节字数不足", log["error"])
        finally:
            conn.close()

    def test_query_uses_volume_id_column(self):
        # Regression: novels.volume_id must exist so the stock path does not
        # crash with OperationalError on every run.
        path = make_db()
        conn = db.connect(path)
        try:
            row = conn.execute(
                "SELECT id, book_id, volume_id FROM novels WHERE id=1"
            ).fetchone()
            self.assertEqual(row["book_id"], "b1")
            self.assertEqual(row["volume_id"], "v1")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
