"""Tests for deleting a Fanqie book (tools/delete_book.py)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from tools import delete_book  # noqa: E402


def make_db(status="publishing", book_id="12345"):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,abstract,tags,protagonists,status,book_id,volume_id) "
        "VALUES('测试书','悬疑脑洞','测试简介','测试简介：一段足够长的简介内容。',"
        "'[\"规则怪谈\"]','[{\"name\":\"林一\"}]',?,?,?)",
        (status, book_id, "v1"),
    )
    conn.commit()
    conn.close()
    return path


def env_ctx():
    return mock.patch(
        "tools.delete_book.load_env",
        return_value={"FANQIE_COOKIE": "cookie=1", "FANQIE_CSRF_TOKEN": "tok"},
    )


class DeleteBookTests(unittest.TestCase):
    def test_reject_missing_novel(self):
        path = make_db()
        conn = db.connect(path)
        try:
            result = delete_book.delete_book_on_fanqie(conn, 999, confirm=True)
            self.assertFalse(result["ok"])
            self.assertIn("not found", result["error"])
        finally:
            conn.close()

    def test_reject_unbound(self):
        path = make_db(book_id="")
        conn = db.connect(path)
        try:
            result = delete_book.delete_book_on_fanqie(conn, 1, confirm=True)
            self.assertFalse(result["ok"])
            self.assertIn("未绑定", result["error"])
        finally:
            conn.close()

    def test_requires_confirmation(self):
        path = make_db()
        conn = db.connect(path)
        try:
            with env_ctx():
                result = delete_book.delete_book_on_fanqie(conn, 1, confirm=False)
            self.assertFalse(result["ok"])
            self.assertIn("二次确认", result["error"])
        finally:
            conn.close()

    def test_reject_when_platform_forbids(self):
        path = make_db()
        conn = db.connect(path)
        responses = [
            {"code": 0, "data": {"can_delete": False, "is_signing": True}},
        ]
        try:
            with env_ctx():
                with mock.patch("tools.delete_book.http_json", side_effect=responses):
                    result = delete_book.delete_book_on_fanqie(conn, 1, confirm=True)
            self.assertFalse(result["ok"])
            self.assertIn("签约中", result["error"])
        finally:
            conn.close()

    def test_delete_and_reset_full_flow(self):
        path = make_db()
        conn = db.connect(path)
        responses = [
            {"code": 0, "data": {"can_delete": True, "is_signing": False}},
            {"code": 0, "data": None},
        ]
        try:
            with env_ctx():
                with mock.patch("tools.delete_book.http_json", side_effect=responses) as http:
                    result = delete_book.delete_book_on_fanqie(conn, 1, confirm=True)
            self.assertTrue(result["ok"], result)
            self.assertEqual(http.call_count, 2)
            delete_call = http.call_args_list[1]
            self.assertEqual(delete_call.args[0], "POST")
            self.assertEqual(delete_call.args[1], "/api/author/book/delete/v0")
            self.assertEqual(delete_call.args[2], {"book_id": "12345"})
            row = conn.execute(
                "SELECT status, book_id, volume_id FROM novels WHERE id=1"
            ).fetchone()
            self.assertEqual(row["status"], "planning")
            self.assertEqual(row["book_id"], "")
            self.assertEqual(row["volume_id"], "")
            logs = conn.execute(
                "SELECT action FROM audit_logs WHERE target_id=1"
            ).fetchall()
            self.assertTrue(any(l["action"] == "delete_book" for l in logs))
        finally:
            conn.close()

    def test_platform_rejection_keeps_local(self):
        path = make_db()
        conn = db.connect(path)
        responses = [
            {"code": 0, "data": {"can_delete": True, "is_signing": False}},
            {"code": 1, "message": "每天只能删除有限数量"},
        ]
        try:
            with env_ctx():
                with mock.patch("tools.delete_book.http_json", side_effect=responses):
                    result = delete_book.delete_book_on_fanqie(conn, 1, confirm=True)
            self.assertFalse(result["ok"])
            self.assertIn("每天只能删除有限数量", result["error"])
            row = conn.execute(
                "SELECT status, book_id FROM novels WHERE id=1"
            ).fetchone()
            self.assertEqual(row["status"], "publishing")
            self.assertEqual(row["book_id"], "12345")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
