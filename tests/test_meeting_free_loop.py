"""Free-meeting event loop tests: ordering, non-blocking submit, dedupe,
heartbeat and fail-closed recovery."""

import os
import tempfile
import time
import unittest

from novel_editorial import db
from tools import meeting_free_loop


class FreeMeetingLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_sessions(kind, topic, novel_id, mode, status, "
                "created_at) VALUES('topic','自由讨论',1,'free','running',"
                "datetime('now','localtime'))"
            )
            self.session_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

    def test_submit_does_not_block_and_processes_in_order(self):
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path)
        processed = []
        original = loop._process_event

        def spy(session_id, event):
            processed.append(event.get("n"))
            original(session_id, event)

        loop._process_event = spy
        started = time.time()
        for i in range(5):
            result = loop.submit_event(self.session_id, {"kind": "user_message", "n": i})
            self.assertTrue(result["ok"])
        self.assertLess(time.time() - started, 1.0)
        deadline = time.time() + 5
        while len(processed) < 5 and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(processed, [0, 1, 2, 3, 4])
        loop.stop(self.session_id)

    def test_duplicate_event_id_processed_once(self):
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path)
        processed = []
        original = loop._process_event

        def spy(session_id, event):
            processed.append(event.get("event_id"))
            original(session_id, event)

        loop._process_event = spy
        first = loop.submit_event(
            self.session_id, {"kind": "user_message", "event_id": "e1"}
        )
        second = loop.submit_event(
            self.session_id, {"kind": "user_message", "event_id": "e1"}
        )
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        deadline = time.time() + 5
        while not processed and time.time() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)
        self.assertEqual(processed.count("e1"), 1)
        loop.stop(self.session_id)

    def test_heartbeat_updated(self):
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path)
        loop.submit_event(self.session_id, {"kind": "user_message"})
        deadline = time.time() + 5
        heartbeat = ""
        while time.time() < deadline:
            conn = db.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT heartbeat_at FROM meeting_sessions WHERE id=?",
                    (self.session_id,),
                ).fetchone()
                heartbeat = row["heartbeat_at"] or ""
            finally:
                conn.close()
            if heartbeat:
                break
            time.sleep(0.05)
        self.assertTrue(heartbeat)
        loop.stop(self.session_id)

    def test_scan_interrupted_marks_running_free_sessions(self):
        conn = db.connect(self.db_path)
        try:
            count = meeting_free_loop.scan_interrupted(conn)
            self.assertEqual(count, 1)
            row = conn.execute(
                "SELECT status FROM meeting_sessions WHERE id=?",
                (self.session_id,),
            ).fetchone()
            self.assertEqual(row["status"], "interrupted")
            audit_rows = conn.execute(
                "SELECT action FROM audit_logs WHERE category='meeting' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchall()
            self.assertEqual(audit_rows[0]["action"], "session_interrupted")
        finally:
            conn.close()

    def test_scan_skips_rounds_sessions(self):
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_sessions(kind, topic, novel_id, mode, status, "
                "created_at) VALUES('weekly','周会',1,'rounds','running',"
                "datetime('now','localtime'))"
            )
            count = meeting_free_loop.scan_interrupted(conn)
            self.assertEqual(count, 1)  # 只处理 free 会话
            row = conn.execute(
                "SELECT status FROM meeting_sessions WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            self.assertEqual(row["status"], "running")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
