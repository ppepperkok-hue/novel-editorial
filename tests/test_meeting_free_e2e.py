"""Free-meeting end-to-end dry run: kickoff event -> speaker -> approval ->
advance event -> finish. Uses mock LLM, a temp DB and the real scheduler."""

import os
import tempfile
import time
import unittest
from unittest import mock

from novel_editorial import db
from novel_editorial.services import meeting_session
from tools import meeting_executor, meeting_free_loop, meeting_speaker


class FreeMeetingE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.reply_calls = []

        def fake_reply(conn_, session_id, agent, event, **kwargs):
            self.reply_calls.append((agent, event.get("kind")))
            seq = conn_.execute(
                "SELECT COALESCE(MAX(seq),0)+1 AS s FROM meeting_messages "
                "WHERE session_id=?",
                (session_id,),
            ).fetchone()["s"]
            cur = conn_.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, from_agent, "
                "role, kind, body, status, created_at) "
                "VALUES(?,0,?,?,'assistant','speech',?,'active',"
                "datetime('now','localtime'))",
                (session_id, seq, agent, f"{agent} 的发言"),
            )
            conn_.commit()
            return {
                "ok": True,
                "spoken": True,
                "message_id": cur.lastrowid,
                "speech": f"{agent} 的发言",
                "interaction_id": None,
            }

        def fake_speakers(conn_, session, event, agent_pool, **kwargs):
            return [
                {"agent": "planner", "reason": "kickoff", "score": 1, "mandatory": False},
                {"agent": "reviewer", "reason": "reply", "score": 1, "mandatory": False},
            ]

        self._patches = [
            mock.patch.object(meeting_executor, "reply_to_mention", fake_reply),
            mock.patch.object(meeting_speaker, "candidate_speakers", fake_speakers),
        ]
        for patch in self._patches:
            patch.start()
        result = meeting_session.start_session_async(
            "讨论下一卷剧情", db_path=self.db_path, kind="topic", mode="free"
        )
        self.assertTrue(result["ok"])
        self.session_id = result["session_id"]

    def tearDown(self):
        meeting_free_loop.get_loop(self.db_path).stop(self.session_id)
        for patch in reversed(self._patches):
            patch.stop()

    def _conn(self):
        return db.connect(self.db_path)

    def _messages(self, conn):
        return conn.execute(
            "SELECT from_agent, kind, body FROM meeting_messages "
            "WHERE session_id=? ORDER BY id",
            (self.session_id,),
        ).fetchall()

    def test_full_loop_with_approval_and_finish(self):
        conn = self._conn()
        try:
            # start_session_async 已提交 kickoff 事件；再投递一条用户消息。
            loop = meeting_free_loop.get_loop(self.db_path)
            loop.submit_event(
                self.session_id,
                {"kind": "user_message", "content": "各位继续", "from_agent": "boss"},
            )
            deadline = time.time() + 8
            count = 0
            status = ""
            while True:
                conn2 = self._conn()
                try:
                    count = conn2.execute(
                        "SELECT COUNT(*) AS c FROM meeting_messages "
                        "WHERE session_id=? AND kind='speech'",
                        (self.session_id,),
                    ).fetchone()["c"]
                    status = conn2.execute(
                        "SELECT status FROM meeting_sessions WHERE id=?",
                        (self.session_id,),
                    ).fetchone()["status"]
                finally:
                    conn2.close()
                if count >= 2 or time.time() > deadline:
                    break
                time.sleep(0.2)
            self.assertGreaterEqual(count, 2)

            # 老板发消息（advance 事件）。
            advanced = meeting_session.advance_session(
                conn, self.session_id, "@守正 回应一下"
            )
            self.assertTrue(advanced["ok"])
            self.assertEqual(advanced["mode"], "free")

            # 结束。
            finished = meeting_session.advance_session(
                conn, self.session_id, "", finish=True
            )
            self.assertTrue(finished["ok"])
            self.assertEqual(finished["status"], "finished")
            row = conn.execute(
                "SELECT status FROM meeting_sessions WHERE id=?",
                (self.session_id,),
            ).fetchone()
            self.assertEqual(row["status"], "finished")
            self.assertEqual(status, "running")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
