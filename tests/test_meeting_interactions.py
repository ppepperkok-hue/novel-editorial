"""Pending interaction tests: request, resolve idempotency, expiry."""

import os
import tempfile
import unittest

from novel_editorial import db
from tools import meeting_interactions


class MeetingInteractionsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_sessions(kind, topic, novel_id, mode, status, "
                "created_at) VALUES('topic','审批测试',1,'free','running',"
                "datetime('now','localtime'))"
            )
            self.session_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

    def _conn(self):
        return db.connect(self.db_path)

    def test_request_and_resolve(self):
        conn = self._conn()
        try:
            result = meeting_interactions.request_interaction(
                conn,
                self.session_id,
                "eic",
                "approval",
                "采纳该经验卡草案？",
                choices=["同意", "拒绝", "暂缓"],
            )
            self.assertTrue(result["ok"])
            interaction_id = result["interaction"]["id"]
            resolved = meeting_interactions.resolve_interaction(
                conn, interaction_id, "同意"
            )
            self.assertTrue(resolved["ok"])
            self.assertFalse(resolved["stale"])
            row = conn.execute(
                "SELECT status, resolution FROM pending_interactions WHERE id=?",
                (interaction_id,),
            ).fetchone()
            self.assertEqual(row["status"], "resolved")
            self.assertEqual(row["resolution"], "同意")
        finally:
            conn.close()

    def test_resolve_twice_is_stale(self):
        conn = self._conn()
        try:
            result = meeting_interactions.request_interaction(
                conn, self.session_id, "eic", "approval", "确认？"
            )
            interaction_id = result["interaction"]["id"]
            meeting_interactions.resolve_interaction(conn, interaction_id, "同意")
            second = meeting_interactions.resolve_interaction(conn, interaction_id, "拒绝")
            self.assertTrue(second["ok"])
            self.assertTrue(second["stale"])
            row = conn.execute(
                "SELECT resolution FROM pending_interactions WHERE id=?",
                (interaction_id,),
            ).fetchone()
            self.assertEqual(row["resolution"], "同意")
        finally:
            conn.close()

    def test_request_validates(self):
        conn = self._conn()
        try:
            bad = meeting_interactions.request_interaction(
                conn, self.session_id, "eic", "nope", "问题"
            )
            self.assertFalse(bad["ok"])
            empty = meeting_interactions.request_interaction(
                conn, self.session_id, "eic", "approval", ""
            )
            self.assertFalse(empty["ok"])
        finally:
            conn.close()

    def test_expire_interactions(self):
        conn = self._conn()
        try:
            result = meeting_interactions.request_interaction(
                conn, self.session_id, "eic", "approval", "过期问题", expires_in=1
            )
            interaction_id = result["interaction"]["id"]
            self.assertEqual(meeting_interactions.expire_interactions(conn), 0)
            row = conn.execute(
                "SELECT status FROM pending_interactions WHERE id=?",
                (interaction_id,),
            ).fetchone()
            self.assertEqual(row["status"], "pending")
            # 直接改过期时间为过去，模拟时间流逝。
            conn.execute(
                "UPDATE pending_interactions SET expires_at='2000-01-01 00:00:00' "
                "WHERE id=?",
                (interaction_id,),
            )
            conn.commit()
            self.assertEqual(meeting_interactions.expire_interactions(conn), 1)
            row = conn.execute(
                "SELECT status FROM pending_interactions WHERE id=?",
                (interaction_id,),
            ).fetchone()
            self.assertEqual(row["status"], "expired")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
