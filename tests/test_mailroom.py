"""S2 tests: mailroom send/list/read/resolve/archive/broadcast/unread."""

import os
import tempfile
import unittest

from novel_pipeline import db
from tools import mailroom


class MailroomTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))
        self.r1 = mailroom.send(
            self.conn, "reviewer", "writer", "第二章逻辑有漏洞，需要返工",
            subject="打回", novel_id=1,
        )
        self.r2 = mailroom.send(
            self.conn, "eic", "writer", "今天两章归你，下午交",
            subject="分派", novel_id=1,
        )
        self.r3 = mailroom.send(
            self.conn, "eic", "reader", "帮我看下第三章钩子",
            subject="求助", novel_id=2,
        )

    def tearDown(self):
        self.conn.close()

    def test_send_requires_fields(self):
        bad = mailroom.send(self.conn, "", "writer", "x")
        self.assertFalse(bad["ok"])
        bad2 = mailroom.send(self.conn, "writer", "reviewer", "   ")
        self.assertFalse(bad2["ok"])

    def test_list_filters_by_agent(self):
        result = mailroom.list_messages(self.conn, agent="writer")
        self.assertTrue(result["ok"])
        ids = [m["id"] for m in result["messages"]]
        self.assertIn(self.r1["id"], ids)
        self.assertIn(self.r2["id"], ids)
        self.assertNotIn(self.r3["id"], ids)

    def test_list_filters_by_novel_and_status(self):
        result = mailroom.list_messages(self.conn, agent="writer", novel_id=1, status="unread")
        self.assertEqual(len(result["messages"]), 2)
        result2 = mailroom.list_messages(self.conn, agent="reader", novel_id=2)
        self.assertEqual(len(result2["messages"]), 1)

    def test_limit_clamped(self):
        result = mailroom.list_messages(self.conn, agent="writer", limit=99999)
        self.assertEqual(len(result["messages"]), 2)
        result2 = mailroom.list_messages(self.conn, agent="writer", limit=1)
        self.assertEqual(len(result2["messages"]), 1)

    def test_unread_count(self):
        count = mailroom.unread_count(self.conn, "writer")
        self.assertEqual(count["unread"], 2)
        count2 = mailroom.unread_count(self.conn, "writer", novel_id=1)
        self.assertEqual(count2["unread"], 2)
        count3 = mailroom.unread_count(self.conn, "reader", novel_id=2)
        self.assertEqual(count3["unread"], 1)

    def test_mark_read(self):
        result = mailroom.mark_read(self.conn, [self.r1["id"], self.r2["id"]])
        self.assertTrue(result["ok"])
        self.assertEqual(result["marked"], 2)
        count = mailroom.unread_count(self.conn, "writer")
        self.assertEqual(count["unread"], 0)
        # Marking again is a no-op for already-read rows.
        result2 = mailroom.mark_read(self.conn, [self.r1["id"]])
        self.assertEqual(result2["marked"], 0)

    def test_resolve(self):
        bad = mailroom.resolve(self.conn, self.r1["id"], "maybe")
        self.assertFalse(bad["ok"])
        result = mailroom.resolve(self.conn, self.r1["id"], "accepted")
        self.assertTrue(result["ok"])
        row = self.conn.execute(
            "SELECT status, resolution FROM agent_messages WHERE id=?",
            (self.r1["id"],),
        ).fetchone()
        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolution"], "accepted")

    def test_archive(self):
        result = mailroom.archive(self.conn, self.r3["id"])
        self.assertTrue(result["ok"])
        row = self.conn.execute(
            "SELECT status FROM agent_messages WHERE id=?", (self.r3["id"],)
        ).fetchone()
        self.assertEqual(row["status"], "archived")
        result2 = mailroom.archive(self.conn, self.r3["id"])
        self.assertEqual(result2["updated"], 0)

    def test_broadcast(self):
        result = mailroom.broadcast(
            self.conn, "eic", ["writer", "reviewer", "memory"],
            "明天十点周会", novel_id=1,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["sent"], 3)


if __name__ == "__main__":
    unittest.main()
