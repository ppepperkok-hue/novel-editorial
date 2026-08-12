"""Free-meeting executor tests: context assembly, speech parsing, retry and audit."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_editorial import db
from tools import meeting_executor


class MeetingExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO meeting_sessions(kind, topic, novel_id, mode, created_at) "
                "VALUES('topic','讨论下一卷剧情',7,'free',"
                "datetime('now','localtime'))"
            )
            self.session_id = cur.lastrowid
            conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, from_agent, "
                "role, kind, body, status, created_at) "
                "VALUES(?,7,1,'planner','assistant','speech','先抛个方向',"
                "'active',datetime('now','localtime'))",
                (self.session_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def _conn(self):
        return db.connect(self.db_path)

    def _messages(self, conn):
        return conn.execute(
            "SELECT * FROM meeting_messages WHERE session_id=? ORDER BY id",
            (self.session_id,),
        ).fetchall()

    def test_parse_speech_skip(self):
        result = meeting_executor.parse_speech('{"speak": false}')
        self.assertFalse(result["spoken"])

    def test_parse_speech_simple(self):
        result = meeting_executor.parse_speech('{"speech": "我觉得可以"}')
        self.assertTrue(result["spoken"])
        self.assertEqual(result["speech"], "我觉得可以")

    def test_parse_speech_six_fields(self):
        raw = json.dumps(
            {
                "weekly_summary": "本周零产出",
                "feelings": "冷静",
                "opinion": "先定规则",
                "concerns": "怕吃书",
                "proposals": ["建台账"],
                "priority": "高",
            },
            ensure_ascii=False,
        )
        result = meeting_executor.parse_speech(raw)
        self.assertTrue(result["spoken"])
        self.assertEqual(result["speech"], "先定规则")
        self.assertEqual(result["structured"]["priority"], "高")

    def test_parse_speech_plain_text(self):
        result = meeting_executor.parse_speech("我觉得可以，先这么定。")
        self.assertTrue(result["spoken"])
        self.assertEqual(result["speech"], "我觉得可以，先这么定。")

    def test_parse_speech_json_block(self):
        result = meeting_executor.parse_speech('```json\n{"speech": "包里的内容"}\n```')
        self.assertEqual(result["speech"], "包里的内容")

    def test_parse_speech_empty(self):
        result = meeting_executor.parse_speech("")
        self.assertFalse(result["spoken"])
        self.assertEqual(result["reason"], "empty")

    def test_reply_speaks_and_persists(self):
        conn = self._conn()
        try:
            result = meeting_executor.reply_to_mention(
                conn,
                self.session_id,
                "reviewer",
                {"kind": "user_message", "content": "@守正 说说顾虑"},
                dry_run=True,
                mock_text='{"speech": "逻辑漏洞在第三章"}',
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["spoken"])
            messages = self._messages(conn)
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[1]["body"], "逻辑漏洞在第三章")
            self.assertEqual(messages[1]["seq"], 2)
            self.assertEqual(messages[1]["novel_id"], 7)
            audit_rows = conn.execute(
                "SELECT action FROM audit_logs WHERE category='meeting' ORDER BY id DESC LIMIT 1"
            ).fetchall()
            self.assertEqual(audit_rows[0]["action"], "speech")
        finally:
            conn.close()

    def test_reply_silence_records_no_speech(self):
        conn = self._conn()
        try:
            result = meeting_executor.reply_to_mention(
                conn,
                self.session_id,
                "reader",
                {"kind": "user_message", "content": "@阿读 说两句"},
                dry_run=True,
                mock_text='{"speak": false}',
            )
            self.assertTrue(result["ok"])
            self.assertFalse(result["spoken"])
            self.assertEqual(len(self._messages(conn)), 1)
            audit_rows = conn.execute(
                "SELECT action FROM audit_logs WHERE category='meeting' ORDER BY id DESC LIMIT 1"
            ).fetchall()
            self.assertEqual(audit_rows[0]["action"], "no_speech")
        finally:
            conn.close()

    def test_reply_retries_once_then_succeeds(self):
        conn = self._conn()
        try:
            calls = {"n": 0}

            def flaky_ask(*args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("network blip")
                return '{"speech": "第二次成功"}', {}, "dry-run", []

            with mock.patch.object(meeting_executor.agent_meeting, "ask", flaky_ask):
                result = meeting_executor.reply_to_mention(
                    conn,
                    self.session_id,
                    "writer",
                    {"kind": "user_message", "content": "@墨白 补充"},
                    dry_run=True,
                )
            self.assertTrue(result["ok"])
            self.assertTrue(result["spoken"])
            self.assertEqual(result["speech"], "第二次成功")
            self.assertEqual(calls["n"], 2)
        finally:
            conn.close()

    def test_reply_fails_twice_and_audits(self):
        conn = self._conn()
        try:
            def broken_ask(*args, **kwargs):
                raise RuntimeError("always down")

            with mock.patch.object(meeting_executor.agent_meeting, "ask", broken_ask):
                result = meeting_executor.reply_to_mention(
                    conn,
                    self.session_id,
                    "writer",
                    {"kind": "user_message", "content": "测试"},
                    dry_run=True,
                )
            self.assertFalse(result["ok"])
            self.assertIn("always down", result["error"])
            self.assertEqual(len(self._messages(conn)), 1)
            audit_rows = conn.execute(
                "SELECT action, detail FROM audit_logs WHERE category='meeting' "
                "ORDER BY id DESC LIMIT 1"
            ).fetchall()
            self.assertEqual(audit_rows[0]["action"], "no_speech")
            self.assertIn("always down", audit_rows[0]["detail"])
        finally:
            conn.close()

    def test_context_includes_history_and_event(self):
        conn = self._conn()
        captured = {}

        def spy_ask(conn_, novel_id, agent, user, **kwargs):
            captured["user"] = user
            return '{"speak": false}', {}, "dry-run", []

        try:
            with mock.patch.object(meeting_executor.agent_meeting, "ask", spy_ask):
                meeting_executor.reply_to_mention(
                    conn,
                    self.session_id,
                    "eic",
                    {"kind": "user_message", "content": "@掌印 拍板"},
                    dry_run=True,
                )
            self.assertIn("讨论下一卷剧情", captured["user"])
            self.assertIn("文策：先抛个方向", captured["user"])
            self.assertIn("老板说：@掌印 拍板", captured["user"])
            self.assertIn("掌印", captured["user"])
        finally:
            conn.close()

    def test_reply_normalizes_md_suffix(self):
        conn = self._conn()
        try:
            result = meeting_executor.reply_to_mention(
                conn,
                self.session_id,
                "reviewer.md",
                {"kind": "user_message", "content": "@守正 回应"},
                dry_run=True,
                mock_text='{"speech": "收到"}',
            )
            self.assertTrue(result["ok"])
            row = conn.execute(
                "SELECT from_agent FROM meeting_messages WHERE id=?",
                (result["message_id"],),
            ).fetchone()
            self.assertEqual(row["from_agent"], "reviewer")
        finally:
            conn.close()

    def test_unique_seq_constraint(self):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, from_agent, "
                "role, kind, body, status, created_at) "
                "VALUES(?,7,99,'planner','assistant','speech','x','active',"
                "datetime('now','localtime'))",
                (self.session_id,),
            )
            conn.commit()
            with self.assertRaises(Exception):
                conn.execute(
                    "INSERT INTO meeting_messages(session_id, novel_id, seq, "
                    "from_agent, role, kind, body, status, created_at) "
                    "VALUES(?,7,99,'writer','assistant','speech','y','active',"
                    "datetime('now','localtime'))",
                    (self.session_id,),
                )
                conn.commit()
        finally:
            conn.close()

    def test_history_truncated_when_over_limit(self):
        conn = self._conn()
        try:
            for i in range(25):
                conn.execute(
                    "INSERT INTO meeting_messages(session_id, novel_id, seq, "
                    "from_agent, role, kind, body, status, created_at) "
                    "VALUES(?,7,?,'planner','assistant','speech',?,'active',"
                    "datetime('now','localtime'))",
                    (self.session_id, 100 + i, "长" * 2000),
                )
            conn.commit()
            session = conn.execute(
                "SELECT * FROM meeting_sessions WHERE id=?", (self.session_id,)
            ).fetchone()
            user = meeting_executor.build_meeting_user(
                conn, session, "reviewer", {"kind": "user_message", "content": "测试"}
            )
            self.assertIn("中间发言已压缩", user)
            self.assertLess(len(user), 40000)
        finally:
            conn.close()

    def test_summarize_history_parses_json(self):
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO meeting_messages(session_id, novel_id, seq, "
                "from_agent, role, kind, body, status, created_at) "
                "VALUES(?,7,2,'planner','assistant','speech','先定方向','active',"
                "datetime('now','localtime'))",
                (self.session_id,),
            )
            conn.commit()
            session = conn.execute(
                "SELECT * FROM meeting_sessions WHERE id=?", (self.session_id,)
            ).fetchone()
            summary = meeting_executor.summarize_history(
                conn,
                session,
                dry_run=True,
                mock_text='{"summary": "决定先定方向，待办：建台账"}',
            )
            self.assertEqual(summary, "决定先定方向，待办：建台账")
        finally:
            conn.close()

    def test_reply_with_approval_request_persists_interaction(self):
        conn = self._conn()
        try:
            result = meeting_executor.reply_to_mention(
                conn,
                self.session_id,
                "eic",
                {"kind": "user_message", "content": "@掌印 给个结论"},
                dry_run=True,
                mock_text=(
                    '{"speech": "我建议采纳", "approval_request": '
                    '{"question": "采纳经验卡草案？", "choices": ["同意", "拒绝"]}}'
                ),
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["spoken"])
            self.assertIsNotNone(result["interaction_id"])
            row = conn.execute(
                "SELECT kind, status FROM pending_interactions WHERE id=?",
                (result["interaction_id"],),
            ).fetchone()
            self.assertEqual(row["kind"], "approval")
            self.assertEqual(row["status"], "pending")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
