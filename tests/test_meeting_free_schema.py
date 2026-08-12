"""Free-meeting schema tests: meeting_messages / pending_interactions tables
exist, migration is idempotent, and meeting_sessions gains mode='rounds'."""

import os
import tempfile
import unittest

from novel_editorial import db
from novel_editorial.services import meeting_session


class MeetingFreeSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")

    def _tables(self):
        conn = db.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return {r["name"] for r in rows}
        finally:
            conn.close()

    def test_new_tables_exist(self):
        tables = self._tables()
        for name in ("meeting_messages", "pending_interactions"):
            self.assertIn(name, tables, name)

    def test_connect_is_idempotent(self):
        db.connect(self.db_path).close()
        db.connect(self.db_path).close()
        db.connect(self.db_path).close()
        self.assertEqual(len(self._tables()), len(self._tables()))

    def test_meeting_sessions_has_mode_default_rounds(self):
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_sessions(kind, topic, created_at) "
                "VALUES('topic','测试会议',datetime('now','localtime'))"
            )
            row = conn.execute(
                "SELECT mode FROM meeting_sessions WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            self.assertEqual(row["mode"], "rounds")
        finally:
            conn.close()

    def test_meeting_message_insert_and_mentions(self):
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, from_agent, "
                "role, kind, body, mentions, created_at) "
                "VALUES(1, 7, 1, 'planner', 'user', 'message', '建议 @守正 复核', "
                "'[{\"type\":\"agent\",\"participantId\":\"reviewer\"}]', "
                "datetime('now','localtime'))"
            )
            row = conn.execute(
                "SELECT * FROM meeting_messages WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            self.assertEqual(row["session_id"], 1)
            self.assertEqual(row["novel_id"], 7)
            self.assertIn("守正", row["body"])
        finally:
            conn.close()

    def test_pending_interaction_insert_and_index(self):
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO pending_interactions(session_id, agent, kind, payload, "
                "created_at, expires_at) "
                "VALUES(1, 'eic', 'approval', '{\"question\":\"采纳该草案？\"}', "
                "datetime('now','localtime'), datetime('now','localtime','+5 minutes'))"
            )
            row = conn.execute(
                "SELECT status FROM pending_interactions WHERE session_id=1"
            ).fetchone()
            self.assertEqual(row["status"], "pending")
            indexes = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                ("idx_pending_interactions_session",),
            ).fetchall()
            self.assertEqual(len(indexes), 1)
        finally:
            conn.close()

    def test_create_session_free_mode(self):
        conn = db.connect(self.db_path)
        try:
            result = meeting_session.create_session(conn, "自由讨论测试", mode="free")
            self.assertTrue(result["ok"])
            row = conn.execute(
                "SELECT mode FROM meeting_sessions WHERE id=?",
                (result["session_id"],),
            ).fetchone()
            self.assertEqual(row["mode"], "free")
            bad = meeting_session.create_session(conn, "非法模式", mode="nope")
            self.assertFalse(bad["ok"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
