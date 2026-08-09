import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from novel_pipeline.services import meeting_session  # noqa: E402


class MeetingSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.path = os.path.join(tmp, "t.db")
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()

    def test_create_requires_topic_and_novel(self):
        r = meeting_session.create_session(self.conn, "  ")
        self.assertFalse(r["ok"])
        r2 = meeting_session.create_session(self.conn, "剧情讨论")
        self.assertFalse(r2["ok"])
        self.assertIn("作品", r2["error"])

    def test_create_and_advance_state_machine(self):
        self.conn.execute(
            "INSERT INTO novels(title,genre,premise,status) VALUES('测试书','都市','x','planning')"
        )
        self.conn.commit()
        r = meeting_session.create_session(self.conn, "讨论主角成长", novel_id=1)
        self.assertTrue(r["ok"])
        sid = r["session_id"]
        s = meeting_session.get_session(self.conn, sid)
        self.assertEqual(s["status"], "running")
        self.assertEqual(s["topic"], "讨论主角成长")

        # advance while running should fail
        r2 = meeting_session.advance_session(self.conn, sid, "继续")
        self.assertFalse(r2["ok"])

        # simulate a finished round -> awaiting input
        self.conn.execute(
            "UPDATE meeting_sessions SET status='awaiting_input' WHERE id=?", (sid,)
        )
        self.conn.commit()
        r3 = meeting_session.advance_session(self.conn, sid, "大家再讨论一下伏笔")
        self.assertTrue(r3["ok"])
        s2 = meeting_session.get_session(self.conn, sid)
        self.assertEqual(s2["status"], "running")
        self.assertEqual(s2["instruction"], "大家再讨论一下伏笔")

    def test_get_session_missing(self):
        self.assertIsNone(meeting_session.get_session(self.conn, 999))


if __name__ == "__main__":
    unittest.main()
