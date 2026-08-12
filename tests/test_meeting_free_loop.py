"""Free-meeting event loop tests: ordering, non-blocking submit, dedupe,
heartbeat and fail-closed recovery."""

import os
import tempfile
import time
import unittest
from unittest import mock

from novel_editorial import db
from tools import meeting_free_loop, meeting_speaker


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

    def _set_attendees(self, conn, agents):
        conn.execute(
            "UPDATE meeting_sessions SET attendees=? WHERE id=?",
            (json_dumps(agents), self.session_id),
        )
        conn.commit()

    def test_event_schedules_candidate_speaker(self):
        conn = db.connect(self.db_path)
        try:
            self._set_attendees(conn, ["planner", "reviewer"])
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        calls = []

        def fake_speakers(*args, **kwargs):
            return [{"agent": "planner", "reason": "interest", "score": 1, "mandatory": False}]

        def fake_reply(conn_, session_id, agent, event, **kwargs):
            calls.append((session_id, agent, event.get("kind")))
            return {"ok": True, "spoken": True, "message_id": 1, "speech": "好"}

        with mock.patch.object(meeting_speaker, "candidate_speakers", fake_speakers), mock.patch.object(
            meeting_free_loop.meeting_executor, "reply_to_mention", fake_reply
        ):
            loop.submit_event(self.session_id, {"kind": "user_message", "content": "讨论"})
            deadline = time.time() + 5
            while not calls and time.time() < deadline:
                time.sleep(0.05)
        self.assertEqual(calls, [(self.session_id, "planner", "user_message")])
        loop.stop(self.session_id)

    def test_breaker_skips_speakers(self):
        conn = db.connect(self.db_path)
        try:
            self._set_attendees(conn, ["planner"])
            for i in range(2):
                conn.execute(
                    "INSERT INTO meeting_messages(session_id, novel_id, seq, "
                    "from_agent, role, kind, body, status, created_at) "
                    "VALUES(?,1,?,'planner','assistant','speech','x','active',"
                    "datetime('now','localtime'))",
                    (self.session_id, i + 1),
                )
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES('meeting_free_max_calls','2')"
            )
            conn.commit()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        calls = []

        def fake_reply(*args, **kwargs):
            calls.append(1)
            return {"ok": True, "spoken": True, "message_id": 1, "speech": "x"}

        with mock.patch.object(
            meeting_free_loop.meeting_executor, "reply_to_mention", fake_reply
        ):
            loop.submit_event(self.session_id, {"kind": "user_message", "content": "讨论"})
            time.sleep(0.6)
        self.assertEqual(calls, [])
        conn = db.connect(self.db_path)
        try:
            audit_rows = conn.execute(
                "SELECT action FROM audit_logs WHERE category='meeting' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchall()
            self.assertEqual(audit_rows[0]["action"], "breaker")
        finally:
            conn.close()
        loop.stop(self.session_id)

    def test_cold_timer_schedules_chair(self):
        conn = db.connect(self.db_path)
        try:
            self._set_attendees(conn, ["eic"])
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES('meeting_free_cold_s','0.2')"
            )
            conn.commit()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        calls = []

        def fake_reply(conn_, session_id, agent, event, **kwargs):
            calls.append((agent, event.get("kind")))
            return {"ok": True, "spoken": True, "message_id": 1, "speech": "推进"}

        with mock.patch.object(
            meeting_free_loop.meeting_executor, "reply_to_mention", fake_reply
        ):
            loop.submit_event(self.session_id, {"kind": "user_message", "content": "开始"})
            deadline = time.time() + 6
            while len(calls) < 2 and time.time() < deadline:
                time.sleep(0.1)
        self.assertIn(("eic", "cold_timer"), calls)
        loop.stop(self.session_id)

    def test_chair_speaks_every_n_messages(self):
        conn = db.connect(self.db_path)
        try:
            self._set_attendees(conn, ["eic", "planner"])
            conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, "
                "from_agent, role, kind, body, status, created_at) "
                "VALUES(?,1,1,'planner','assistant','speech','第一条','active',"
                "datetime('now','localtime'))"
                ,
                (self.session_id,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) "
                "VALUES('meeting_free_chair_every_n','1')"
            )
            conn.commit()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        calls = []

        def fake_speakers(*args, **kwargs):
            return []

        def fake_reply(conn_, session_id, agent, event, **kwargs):
            calls.append(agent)
            return {"ok": True, "spoken": True, "message_id": 1, "speech": "插话"}

        with mock.patch.object(meeting_speaker, "candidate_speakers", fake_speakers), mock.patch.object(
            meeting_free_loop.meeting_executor, "reply_to_mention", fake_reply
        ):
            loop.submit_event(self.session_id, {"kind": "user_message", "content": "讨论"})
            deadline = time.time() + 5
            while "eic" not in calls and time.time() < deadline:
                time.sleep(0.05)
        self.assertIn("eic", calls)
        loop.stop(self.session_id)

    def test_history_compress_runs_once_and_is_idempotent(self):
        conn = db.connect(self.db_path)
        try:
            self._set_attendees(conn, ["planner"])
            for i in range(20):
                conn.execute(
                    "INSERT INTO meeting_messages(session_id, novel_id, seq, "
                    "from_agent, role, kind, body, status, created_at) "
                    "VALUES(?,1,?,'planner','assistant','speech',?,'active',"
                    "datetime('now','localtime'))",
                    (self.session_id, i + 1, "长" * 2000),
                )
            conn.commit()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        with mock.patch.object(
            meeting_free_loop.meeting_executor,
            "summarize_history",
            return_value="会议要点摘要",
        ):
            loop.submit_event(self.session_id, {"kind": "user_message", "content": "讨论"})
            deadline = time.time() + 6
            summary = ""
            while time.time() < deadline:
                conn = db.connect(self.db_path)
                try:
                    row = conn.execute(
                        "SELECT meeting_summary FROM meeting_sessions WHERE id=?",
                        (self.session_id,),
                    ).fetchone()
                    summary = row["meeting_summary"] or ""
                finally:
                    conn.close()
                if summary:
                    break
                time.sleep(0.1)
            self.assertEqual(summary, "会议要点摘要")
            conn = db.connect(self.db_path)
            compressed = conn.execute(
                "SELECT COUNT(*) AS c FROM meeting_messages "
                "WHERE session_id=? AND compressed_at!=''",
                (self.session_id,),
            ).fetchone()["c"]
            conn.close()
            self.assertEqual(compressed, 20)
        loop.stop(self.session_id)

    def test_compress_skipped_when_summary_exists(self):
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE meeting_sessions SET meeting_summary='已有摘要' WHERE id=?",
                (self.session_id,),
            )
            conn.commit()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        calls = []
        conn = db.connect(self.db_path)
        with mock.patch.object(
            meeting_free_loop.meeting_executor,
            "summarize_history",
            side_effect=lambda *a, **k: calls.append(1) or "x",
        ):
            try:
                session = conn.execute(
                    "SELECT * FROM meeting_sessions WHERE id=?", (self.session_id,)
                ).fetchone()
                self.assertFalse(loop._maybe_compress(conn, session))
            finally:
                conn.close()
        self.assertEqual(calls, [])
        loop.stop(self.session_id)

    def test_breaker_scoped_to_novel(self):
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO cost_logs(novel_id, node_name, cost, created_at) "
                "VALUES(2,'other',100,datetime('now','localtime'))"
            )
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) "
                "VALUES('meeting_free_max_cost','50')"
            )
            conn.commit()
            session = conn.execute(
                "SELECT * FROM meeting_sessions WHERE id=?", (self.session_id,)
            ).fetchone()
            loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path)
            self.assertFalse(loop._breaker_hit(conn, session))
            conn.execute(
                "INSERT INTO cost_logs(novel_id, node_name, cost, created_at) "
                "VALUES(1,'meeting',100,datetime('now','localtime'))"
            )
            conn.commit()
            self.assertTrue(loop._breaker_hit(conn, session))
        finally:
            conn.close()

    def test_stop_waits_for_inflight_speakers(self):
        conn = db.connect(self.db_path)
        try:
            self._set_attendees(conn, ["planner"])
            session = conn.execute(
                "SELECT * FROM meeting_sessions WHERE id=?", (self.session_id,)
            ).fetchone()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        calls = []

        def slow_reply(*args, **kwargs):
            time.sleep(0.4)
            calls.append("spoke")
            return {"ok": True, "spoken": True, "message_id": 1, "speech": "慢"}

        with mock.patch.object(
            meeting_free_loop.meeting_executor, "reply_to_mention", slow_reply
        ):
            loop._run_candidates(
                conn,
                session,
                [{"agent": "planner", "reason": "test", "score": 1, "mandatory": False}],
                {"kind": "user_message", "content": "测试"},
            )
            loop.stop(self.session_id)
        self.assertEqual(calls, ["spoke"])
        self.assertEqual(loop.running_agents(self.session_id), set())

    def test_heartbeat_expires_stale_interactions(self):
        conn = db.connect(self.db_path)
        try:
            from tools import meeting_interactions

            created = meeting_interactions.request_interaction(
                conn, self.session_id, "eic", "approval", "过期确认"
            )
            interaction_id = created["interaction"]["id"]
            conn.execute(
                "UPDATE pending_interactions SET expires_at='2000-01-01 00:00:00' "
                "WHERE id=?",
                (interaction_id,),
            )
            conn.commit()
        finally:
            conn.close()
        loop = meeting_free_loop.FreeMeetingLoop(db_path=self.db_path, dry_run=True)
        loop.submit_event(self.session_id, {"kind": "user_message", "content": "触发心跳"})
        deadline = time.time() + 5
        status = ""
        while time.time() < deadline:
            conn = db.connect(self.db_path)
            try:
                row = conn.execute(
                    "SELECT status FROM pending_interactions WHERE id=?",
                    (interaction_id,),
                ).fetchone()
                status = row["status"]
            finally:
                conn.close()
            if status == "expired":
                break
            time.sleep(0.1)
        self.assertEqual(status, "expired")
        loop.stop(self.session_id)


def json_dumps(agents):
    import json

    return json.dumps(agents, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
