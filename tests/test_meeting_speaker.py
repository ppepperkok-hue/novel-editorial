"""Speaker candidacy tests: mandatory mentions, interest ranking, caps,
sender/busy/cooldown exclusions."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta

from novel_editorial import db
from tools import meeting_speaker


class MeetingSpeakerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_sessions(kind, topic, novel_id, mode, status, "
                "created_at) VALUES('topic','讨论下一卷剧情',1,'free','running',"
                "datetime('now','localtime'))"
            )
            self.session_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

    def _session(self, conn):
        return conn.execute(
            "SELECT * FROM meeting_sessions WHERE id=?", (self.session_id,)
        ).fetchone()

    def _conn(self):
        return db.connect(self.db_path)

    POOL = ["planner", "guard", "writer", "editor", "reviewer", "reader",
            "eic", "memory", "work_meta", "ending_judge", "knowledge_keeper"]

    def test_mentioned_agent_is_mandatory(self):
        conn = self._conn()
        try:
            event = {"kind": "user_message", "content": "@守正 说说你的顾虑"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL
            )
            reviewer = next(c for c in candidates if c["agent"] == "reviewer")
            self.assertTrue(reviewer["mandatory"])
            self.assertEqual(reviewer["reason"], "mentioned")
        finally:
            conn.close()

    def test_interest_based_candidates_without_mention(self):
        conn = self._conn()
        try:
            event = {"kind": "user_message", "content": "下一卷的剧情走向怎么定？"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL
            )
            agents = [c["agent"] for c in candidates]
            self.assertIn("planner", agents)  # 剧情/方向命中
            self.assertNotIn("ending_judge", agents)  # 完结词未命中
        finally:
            conn.close()

    def test_non_mandatory_cap(self):
        conn = self._conn()
        try:
            event = {"kind": "user_message", "content": "逻辑漏洞和读者体验都要考虑"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL, k=2
            )
            non_mandatory = [c for c in candidates if not c["mandatory"]]
            self.assertLessEqual(len(non_mandatory), 2)
        finally:
            conn.close()

    def test_sender_is_excluded(self):
        conn = self._conn()
        try:
            event = {"kind": "agent_message", "from_agent": "planner", "content": "我觉得剧情这样走"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL
            )
            self.assertNotIn("planner", [c["agent"] for c in candidates])
        finally:
            conn.close()

    def test_busy_agents_are_excluded(self):
        conn = self._conn()
        try:
            event = {"kind": "user_message", "content": "@守正 说"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL, busy=("reviewer",)
            )
            self.assertNotIn("reviewer", [c["agent"] for c in candidates])
        finally:
            conn.close()

    def test_cooldown_excludes_recent_speaker(self):
        conn = self._conn()
        try:
            now = datetime.now()
            conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, from_agent, "
                "role, kind, body, status, created_at) "
                "VALUES(?,1,1,'planner','assistant','speech','刚说过',"
                "'active',?)",
                (self.session_id, (now - timedelta(seconds=10)).strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            event = {"kind": "user_message", "content": "剧情方向"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL, cooldown_s=60
            )
            self.assertNotIn("planner", [c["agent"] for c in candidates])
        finally:
            conn.close()

    def test_ranking_puts_mandatory_first(self):
        conn = self._conn()
        try:
            event = {"kind": "user_message", "content": "@掌印 拍板，剧情逻辑读者都要考虑"}
            candidates = meeting_speaker.candidate_speakers(
                conn, self._session(conn), event, self.POOL
            )
            self.assertEqual(candidates[0]["agent"], "eic")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
