import os
import sys
import tempfile
import unittest
from unittest import mock

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
        ):
            meeting_session._run_locked(self.conn, sid)

        s = meeting_session.get_session(self.conn, sid)
        self.assertEqual(s["status"], "finished")
        self.assertEqual(len(s["transcript"]), 18)
        row = self.conn.execute(
            "SELECT novel_id, report FROM weekly_meetings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["novel_id"], 0)
        report = json.loads(row["report"])
        self.assertEqual(report["decisions"]["next_book"]["book_name"], "测试新书")
        n = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_diaries WHERE diary_type='meeting'"
        ).fetchone()["c"]
        self.assertEqual(n, 6)

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
