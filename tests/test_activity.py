import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_editorial import db  # noqa: E402
from novel_editorial.services import activity  # noqa: E402


class ActivityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.path = os.path.join(tmp, "t.db")
        self.conn = db.connect(self.path)

    def tearDown(self):
        self.conn.close()

    def test_schema_has_actions_and_activity(self):
        action_cols = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(agent_actions)").fetchall()
        }
        self.assertIn("task", action_cols)
        self.assertIn("status", action_cols)
        self.assertIn("session_id", action_cols)
        self.assertIn("meeting_id", action_cols)
        activity_cols = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(agent_activity)").fetchall()
        }
        self.assertIn("activity_type", activity_cols)
        self.assertIn("title", activity_cols)

    def test_log_and_list_activity_grouped_by_day(self):
        activity.log_activity(
            self.conn, "writer", 1, "meeting_speech", "会议第 1 轮发言",
            {"speech": "先写钩子"},
        )
        activity.log_activity(
            self.conn, "eic", 1, "meeting_summary", "主席总结会议",
            {"summary": "结论"},
        )
        rows = activity.list_activity(self.conn, agent="writer")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["activity_type"], "meeting_speech")
        self.assertEqual(rows[0]["detail"]["speech"], "先写钩子")
        days = activity.activity_days(self.conn)
        self.assertEqual(len(days), 1)
        self.assertEqual(len(days[0]["items"]), 2)
        rows = activity.list_activity(self.conn, day=days[0]["date"])
        self.assertEqual(len(rows), 2)

    def test_action_lifecycle(self):
        r = activity.create_action(
            self.conn, "guard", "建立伏笔台账", novel_id=3, session_id=7,
            meeting_id=9, detail={"due": "3天内"},
        )
        self.assertTrue(r["ok"])
        aid = r["id"]
        rows = activity.list_actions(self.conn, agent="guard", status="pending")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["detail"]["due"], "3天内")
        self.assertTrue(activity.update_action(self.conn, aid, "done", "台账已建")["ok"])
        done = activity.list_actions(self.conn, status="done")
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0]["result"], "台账已建")
        self.assertTrue(done[0]["completed_at"])
        self.assertFalse(activity.update_action(self.conn, aid, "bogus")["ok"])

    def test_post_meeting_actions_assigns_report_items(self):
        report = {
            "discussion_summary": "定下规则怪谈",
            "action_items": [
                {"task": "guard 建三本台账", "owner": "guard"},
                {"task": "writer 写开篇三连击", "owner": "writer"},
            ],
        }
        transcript = [
            {"agent": "guard", "speech": {"speech": "我支持台账", "proposals": ["建台账"]}},
            {"agent": "writer", "speech": {"speech": "我来写", "proposals": ["写钩子"]}},
        ]
        res = activity.generate_post_meeting_actions(
            self.conn, 7, 9, 1, ["guard", "writer"], report, transcript, dry_run=True
        )
        self.assertEqual(res["ok"], True)
        rows = activity.list_actions(self.conn, status="pending")
        self.assertEqual(len(rows), 2)
        by_agent = {a["agent"]: a["task"] for a in rows}
        self.assertIn("guard", by_agent)
        self.assertIn("writer", by_agent)

    def test_post_meeting_actions_fallback_when_report_empty(self):
        res = activity.generate_post_meeting_actions(
            self.conn, 1, 1, 1, ["memory"], {"action_items": [], "discussion_summary": ""},
            [{"agent": "memory", "speech": {"speech": "无结论"}}],
            dry_run=True,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["created"], 1)
        rows = activity.list_actions(self.conn, agent="memory")
        self.assertEqual(rows[0]["status"], "pending")

    def test_post_meeting_actions_llm_failure_falls_back(self):
        with mock.patch(
            "novel_editorial.services.activity.chat_deepseek",
            side_effect=RuntimeError("api down"),
        ):
            res = activity.generate_post_meeting_actions(
                self.conn, 1, 1, 1, ["writer"],
                {"action_items": [], "discussion_summary": ""},
                [{"agent": "writer", "speech": {"speech": "x"}}],
                dry_run=False,
            )
        self.assertTrue(res["ok"])
        self.assertEqual(len(activity.list_actions(self.conn, agent="writer")), 1)

    def test_post_meeting_actions_system_includes_persona(self):
        captured = {}
        from novel_editorial.services import activity as act

        def fake_chat(model, system, user, temperature=0.5, max_tokens=1600):
            captured["system"] = system
            return {
                "text": json.dumps([{"task": "落实会议结论"}]),
                "usage": {},
                "model": "mock",
            }

        with mock.patch(
            "novel_editorial.services.activity.chat_deepseek",
            side_effect=fake_chat,
        ):
            act.generate_post_meeting_actions(
                self.conn, 1, 1, 1, ["writer"],
                {"action_items": []}, [{"agent": "writer", "speech": {}}],
                dry_run=False,
            )
        self.assertIn("人物档案", captured["system"])
        self.assertIn("墨白", captured["system"])

    def test_llm_parsed_tasks_are_used(self):
        with mock.patch(
            "novel_editorial.services.activity.chat_deepseek",
            return_value={
                "text": json.dumps(
                    [
                        {"task": "整理规则书", "reason": "会上定的", "expected_output": "md 文件", "due": "3天"},
                    ],
                    ensure_ascii=False,
                ),
                "usage": {},
                "model": "mock",
            },
        ):
            res = activity.generate_post_meeting_actions(
                self.conn, 2, 2, 1, ["guard"],
                {"action_items": [{"task": "guard 建台账"}]},
                [{"agent": "guard", "speech": {"speech": "x"}}],
                dry_run=False,
            )
        self.assertEqual(res["created"], 1)
        rows = activity.list_actions(self.conn, agent="guard")
        self.assertEqual(rows[0]["task"], "整理规则书")
        self.assertEqual(rows[0]["detail"]["due"], "3天")

