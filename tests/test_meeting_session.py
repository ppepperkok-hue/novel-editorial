import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_editorial import db  # noqa: E402
from novel_editorial.services import meeting_session  # noqa: E402


class MeetingSessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.path = os.path.join(tmp, "t.db")
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()

    def test_parse_json_repairs_truncated_speech(self):
        from tools.agent_meeting import parse_json  # noqa: E402

        full = '{"speech": "hello", "weekly_summary": "ok", "feelings": "calm"}'
        self.assertEqual(parse_json(full)["speech"], "hello")

        truncated = '{"speech": "hello world", "weekly_summary": "this text is cut'
        obj = parse_json(truncated)
        self.assertIsNotNone(obj)
        self.assertEqual(obj.get("speech"), "hello world")

        unterminated = '{"speech": "hello", "weekly_summary": "x"'
        obj2 = parse_json(unterminated)
        self.assertIsNotNone(obj2)
        self.assertEqual(obj2.get("speech"), "hello")

        self.assertIsNone(parse_json("not json at all"))

    def test_create_requires_topic(self):
        r = meeting_session.create_session(self.conn, "  ")
        self.assertFalse(r["ok"])
        r2 = meeting_session.create_session(self.conn, "第一本书写什么")
        self.assertTrue(r2["ok"])

    def test_create_without_novel_is_planning_meeting(self):
        r = meeting_session.create_session(self.conn, "讨论新书选题")
        self.assertTrue(r["ok"])
        s = meeting_session.get_session(self.conn, r["session_id"])
        self.assertEqual(s["novel_id"], 0)
        self.assertEqual(s["status"], "running")

    def test_topic_request_becomes_action_and_archived(self):
        from tools import mailroom  # noqa: E402

        r = mailroom.send(
            self.conn, "guard", "eic", "规则台账模板需要统一",
            subject="议题提议", kind="topic_request",
        )
        self.assertTrue(r["ok"])
        created = meeting_session._persist_topic_request_actions(self.conn, 1, 2, 0)
        self.assertEqual(created, 1)
        actions = self.conn.execute(
            "SELECT agent, task, session_id, meeting_id FROM agent_actions"
        ).fetchall()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["agent"], "guard")
        self.assertIn("规则台账模板", actions[0]["task"])
        self.assertEqual(actions[0]["session_id"], 1)
        self.assertEqual(actions[0]["meeting_id"], 2)
        row = self.conn.execute(
            "SELECT status FROM agent_messages WHERE kind='topic_request'"
        ).fetchone()
        self.assertEqual(row["status"], "archived")

    def test_repeat_close_is_idempotent(self):
        from tools import mailroom  # noqa: E402

        mailroom.send(self.conn, "reader", "eic", "某章会掉读", kind="topic_request")
        self.assertEqual(
            meeting_session._persist_topic_request_actions(self.conn, 1, 2, 0), 1
        )
        self.assertEqual(
            meeting_session._persist_topic_request_actions(self.conn, 1, 2, 0), 0
        )
        n = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_actions"
        ).fetchone()["c"]
        self.assertEqual(n, 1)

    def test_switch_off_creates_nothing(self):
        from tools import mailroom  # noqa: E402

        mailroom.send(self.conn, "guard", "eic", "测试议题", kind="topic_request")
        with mock.patch(
            "novel_editorial.services.meeting_session.config.TOPIC_REQUEST_ACTIONS",
            False,
        ):
            created = meeting_session._persist_topic_request_actions(
                self.conn, 1, 2, 0
            )
        self.assertEqual(created, 0)
        n = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_actions"
        ).fetchone()["c"]
        self.assertEqual(n, 0)

    def test_meeting_agency_and_outbox_executed(self):
        speech = {
            "speech": "我提议把规则台账模板定死",
            "agency": [
                {"action": "write_report", "body": "设定冲突检查报告"},
                {"action": "post_issue", "body": "规则台账模板需要统一"},
            ],
            "outbox": [
                {"to": "eic", "body": "请审阅我的报告", "subject": "报告"}
            ],
        }
        meeting_session._handle_meeting_actions(self.conn, "guard", 1, speech)
        activity_rows = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_activity "
            "WHERE agent='guard' AND activity_type='agency_report'"
        ).fetchone()["c"]
        self.assertEqual(activity_rows, 1)
        issue = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_messages "
            "WHERE from_agent='guard' AND kind='topic_request'"
        ).fetchone()["c"]
        self.assertEqual(issue, 1)
        msg = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_messages "
            "WHERE from_agent='guard' AND kind='note'"
        ).fetchone()["c"]
        self.assertEqual(msg, 1)

    def test_meeting_memory_used_persisted(self):
        speech = {
            "speech": "我引用了上周周记的结论",
            "memory_used": ["上周我说过规则怪谈不能只靠爽点"],
        }
        meeting_session._handle_meeting_actions(self.conn, "writer", 1, speech)
        row = self.conn.execute(
            "SELECT activity_type, title FROM agent_activity "
            "WHERE agent='writer' AND activity_type='memory_used'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("规则怪谈", row["title"])

    def test_meeting_malformed_agency_does_not_crash(self):
        speech = {
            "speech": "x",
            "agency": "不是数组",
            "outbox": {"to": "eic"},
            "memory_used": ["上周结论"],
        }
        result = meeting_session._handle_meeting_actions(self.conn, "writer", 1, speech)
        self.assertIsNone(result)
        agency_rows = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_activity "
            "WHERE agent='writer' AND activity_type='agency_report'"
        ).fetchone()["c"]
        self.assertEqual(agency_rows, 0)
        audit_rows = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE category='agency'"
        ).fetchone()["c"]
        self.assertEqual(audit_rows, 0)
        msgs = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_messages WHERE from_agent='writer'"
        ).fetchone()["c"]
        self.assertEqual(msgs, 0)
        memory = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_activity "
            "WHERE agent='writer' AND activity_type='memory_used'"
        ).fetchone()["c"]
        self.assertEqual(memory, 1)

    def test_planning_meeting_full_chain_without_novel(self):
        import json

        from tools import agent_meeting

        r = meeting_session.create_session(self.conn, "第一本书写什么")
        self.assertTrue(r["ok"])
        sid = r["session_id"]

        def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                     max_tokens=1600, tools=None, messages=None, system_override=None):
            if agent == "eic" and "决定本次参会名单" in user:
                text = json.dumps(
                    {
                        "attendees": ["planner", "reader", "memory", "guard", "writer", "eic"],
                        "topics": ["新书选题", "卖点", "开篇钩子"],
                    },
                    ensure_ascii=False,
                )
            elif agent == "eic" and "请总结本次周会" in user:
                text = json.dumps(
                    {
                        "meeting_id": "t",
                        "date": "2026-08-10 10:00:00",
                        "attendees": [],
                        "topics": [],
                        "discussion_summary": "选题会结论：写都市脑洞文",
                        "decisions": {
                            "blueprint_updates": [],
                            "volume_goal_adjust": "",
                            "next_book": {
                                "book_name": "测试新书",
                                "genre": "都市",
                                "abstract": "x",
                                "selling_point": "y",
                                "protagonist": "z",
                            },
                        },
                        "disagreements": [],
                        "action_items": [],
                    },
                    ensure_ascii=False,
                )
            else:
                text = json.dumps(
                    {
                        "weekly_summary": f"{agent} 选题会小结",
                        "feelings": "期待",
                        "opinion": "支持新书方向",
                        "concerns": [],
                        "proposals": ["确定题材后建书"],
                        "priority": "高",
                    },
                    ensure_ascii=False,
                )
            return text, {"prompt_tokens": 1, "completion_tokens": 1}, "mock", []

        waits = {"n": 0}

        def fake_sleep(secs):
            # Each pause between rounds: advance the session as a user would.
            waits["n"] += 1
            if waits["n"] <= 2:
                self.conn.execute(
                    "UPDATE meeting_sessions SET status='running', instruction='继续', "
                    "updated_at=datetime('now','localtime') WHERE id=?",
                    (sid,),
                )
                self.conn.commit()
            elif waits["n"] == 3:
                # user decides round 3 is the last one: finish and summarize
                self.conn.execute(
                    "UPDATE meeting_sessions SET status='running', instruction=?, "
                    "updated_at=datetime('now','localtime') WHERE id=?",
                    (meeting_session.FINISH_TOKEN, sid),
                )
                self.conn.commit()

        with (
            mock.patch("tools.agent_meeting.ask", side_effect=fake_ask),
            mock.patch("time.sleep", side_effect=fake_sleep),
            mock.patch(
                "novel_editorial.services.activity.chat_deepseek",
                side_effect=RuntimeError("offline"),
            ),
        ):
            meeting_session._run_locked(self.conn, sid)

        s = meeting_session.get_session(self.conn, sid)
        self.assertEqual(s["status"], "finished")
        self.assertEqual(len(s["transcript"]), 18)
        row = self.conn.execute(
            "SELECT novel_id, report FROM weekly_meetings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        audit = self.conn.execute(
            "SELECT detail FROM audit_logs WHERE category='meeting' "
            "AND action='completed' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(audit, "meeting completion must be audited")
        audit_detail = json.loads(audit["detail"])
        self.assertIn("meeting_id", audit_detail)
        self.assertEqual(row["novel_id"], 0)
        report = json.loads(row["report"])
        self.assertEqual(report["decisions"]["next_book"]["book_name"], "测试新书")
        n = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_diaries WHERE diary_type='meeting'"
        ).fetchone()["c"]
        self.assertEqual(n, 6)
        # Post-meeting actions fall back to rule-based assignment on LLM failure.
        n_actions = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_actions WHERE status='pending'"
        ).fetchone()["c"]
        self.assertEqual(n_actions, 6)
        # Activity trace covers every speech plus the chair summary.
        n_speech = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_activity WHERE activity_type='meeting_speech'"
        ).fetchone()["c"]
        self.assertGreaterEqual(n_speech, 18)
        n_summary = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_activity WHERE activity_type='meeting_summary'"
        ).fetchone()["c"]
        self.assertEqual(n_summary, 1)
        weekly = self.conn.execute(
            "SELECT session_id FROM weekly_meetings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(weekly["session_id"], sid)
        # New-book meeting conclusions become a planning novel automatically.
        nb = self.conn.execute(
            "SELECT id, title, status FROM novels WHERE status='planning'"
        ).fetchone()
        self.assertIsNotNone(nb)
        self.assertEqual(nb["title"], "测试新书")

    def test_session_times_out_after_hard_limit(self):
        from tools import agent_meeting

        r = meeting_session.create_session(self.conn, "超时测试")
        sid = r["session_id"]
        self.conn.execute(
            "UPDATE meeting_sessions SET attendees='[\"eic\"]', "
            "current_round=0 WHERE id=?", (sid,)
        )
        self.conn.commit()
        old = meeting_session.MEETING_TIMEOUT_SECONDS
        meeting_session.MEETING_TIMEOUT_SECONDS = -1
        try:
            with (
                mock.patch("tools.agent_meeting.ask"),
                mock.patch("time.sleep"),
            ):
                meeting_session._run_locked(self.conn, sid)
        finally:
            meeting_session.MEETING_TIMEOUT_SECONDS = old
        s = meeting_session.get_session(self.conn, sid)
        self.assertEqual(s["status"], "failed")
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE action='session_timeout'"
        ).fetchone()
        self.assertEqual(row["c"], 1)

    def test_advance_with_finish_flag(self):
        self.conn.execute(
            "INSERT INTO meeting_sessions(kind,topic,status,novel_id,created_at,updated_at) "
            "VALUES('topic','x','awaiting_input',0,datetime('now','localtime'),datetime('now','localtime'))"
        )
        self.conn.commit()
        sid = self.conn.execute("SELECT id FROM meeting_sessions ORDER BY id DESC LIMIT 1").fetchone()["id"]
        r = meeting_session.advance_session(self.conn, sid, "继续讨论", finish=True)
        self.assertTrue(r["ok"])
        s = meeting_session.get_session(self.conn, sid)
        self.assertEqual(s["status"], "running")
        self.assertEqual(s["instruction"], meeting_session.FINISH_TOKEN)

    def test_second_meeting_rejected_while_one_is_active(self):
        r1 = meeting_session.create_session(self.conn, "first meeting")
        self.assertTrue(r1["ok"])
        r2 = meeting_session.create_session(self.conn, "second meeting")
        self.assertFalse(r2["ok"])
        self.assertIn("已有会议进行中", r2["error"])

    def test_stale_running_session_self_heals(self):
        stale = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.gmtime(time.time() - 3600)
        )
        cur = self.conn.execute(
            "INSERT INTO meeting_sessions(kind,topic,status,novel_id,heartbeat_at,created_at,updated_at) "
            "VALUES('topic','stale','running',0,?,?,?)",
            (stale, "2026-08-10 10:00:00", "2026-08-10 10:00:00"),
        )
        self.conn.commit()
        sid = cur.lastrowid
        active = meeting_session.get_active_session(self.conn)
        self.assertIsNone(active)
        row = self.conn.execute(
            "SELECT status FROM meeting_sessions WHERE id=?", (sid,)
        ).fetchone()
        self.assertEqual(row["status"], "failed")

    def test_cancel_during_speech_not_overwritten_by_awaiting(self):
        cur = self.conn.execute(
            "INSERT INTO meeting_sessions(kind,topic,status,novel_id,created_at,updated_at) "
            "VALUES('topic','cancel-test','cancelled',0,datetime('now','localtime'),datetime('now','localtime'))"
        )
        self.conn.commit()
        sid = cur.lastrowid
        cur2 = self.conn.execute(
            "UPDATE meeting_sessions SET status='awaiting_input', instruction='', "
            "updated_at=? WHERE id=? AND status != 'cancelled'",
            (time.strftime("%Y-%m-%d %H:%M:%S"), sid),
        )
        self.conn.commit()
        self.assertEqual(cur2.rowcount, 0)
        row = self.conn.execute(
            "SELECT status FROM meeting_sessions WHERE id=?", (sid,)
        ).fetchone()
        self.assertEqual(row["status"], "cancelled")

    def test_get_active_session_returns_latest_in_progress(self):
        self.assertIsNone(meeting_session.get_active_session(self.conn))
        r = meeting_session.create_session(self.conn, "进行中的会")
        self.assertTrue(r["ok"])
        active = meeting_session.get_active_session(self.conn)
        self.assertEqual(active["id"], r["session_id"])
        self.assertEqual(active["status"], "running")

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
