"""S8 tests: task-board columns, claiming, status machine and permissions."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from novel_editorial import db
from novel_editorial.services import activity
from tools import agent_context
from tools import auto_fill_actions


class AgentActionsTests(unittest.TestCase):
    def test_claim_rejects_inconsistent_state_atomically(self):
        self.conn.execute(
            "UPDATE agent_actions SET status='claimed', claimed_by='' "
            "WHERE id=?",
            (self.action_id,),
        )
        self.conn.commit()
        result = activity.claim_action(
            self.conn, self.action_id, "reviewer", novel_id=1
        )
        self.assertFalse(result["ok"])
        row = self.conn.execute(
            "SELECT claimed_by, status FROM agent_actions WHERE id=?",
            (self.action_id,),
        ).fetchone()
        self.assertEqual(row["claimed_by"], "")

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        self.action_id = activity.create_action(
            self.conn, "writer", "把规则台账模板定死", novel_id=1,
            assignee="writer", priority="high", due_at="2026-08-20",
        )["id"]

    def tearDown(self):
        self.conn.close()

    def test_new_columns_exist(self):
        cols = {
            r["name"]
            for r in self.conn.execute("PRAGMA table_info(agent_actions)").fetchall()
        }
        for col in ("assignee", "claimed_by", "priority", "due_at", "blocked_by"):
            self.assertIn(col, cols)
        row = self.conn.execute(
            "SELECT assignee, priority, due_at FROM agent_actions WHERE id=?",
            (self.action_id,),
        ).fetchone()
        self.assertEqual(row["assignee"], "writer")
        self.assertEqual(row["priority"], "high")
        self.assertEqual(row["due_at"], "2026-08-20")

    def test_claim_success_and_state_machine(self):
        result = activity.claim_action(self.conn, self.action_id, "writer", novel_id=1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "claimed")
        row = self.conn.execute(
            "SELECT status, claimed_by FROM agent_actions WHERE id=?",
            (self.action_id,),
        ).fetchone()
        self.assertEqual(row["status"], "claimed")
        self.assertEqual(row["claimed_by"], "writer")
        # Claimed actions cannot be claimed again.
        again = activity.claim_action(self.conn, self.action_id, "reviewer", novel_id=1)
        self.assertFalse(again["ok"])
        self.assertIn("already claimed", again["error"])
        # The claimant can move it to in_progress then done.
        r1 = activity.update_action(self.conn, self.action_id, "in_progress", agent="writer")
        self.assertTrue(r1["ok"])
        r2 = activity.update_action(self.conn, self.action_id, "done", result="完成", agent="writer")
        self.assertTrue(r2["ok"])
        row = self.conn.execute(
            "SELECT status, result FROM agent_actions WHERE id=?",
            (self.action_id,),
        ).fetchone()
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["result"], "完成")

    def test_claim_rejects_wrong_novel(self):
        result = activity.claim_action(self.conn, self.action_id, "writer", novel_id=9)
        self.assertFalse(result["ok"])
        self.assertIn("another novel", result["error"])

    def test_claim_missing_action(self):
        result = activity.claim_action(self.conn, 999999, "writer")
        self.assertFalse(result["ok"])
        self.assertIn("not found", result["error"])

    def test_update_permission_enforced(self):
        activity.claim_action(self.conn, self.action_id, "writer", novel_id=1)
        denied = activity.update_action(self.conn, self.action_id, "in_progress", agent="reviewer")
        self.assertFalse(denied["ok"])
        self.assertIn("not the assignee", denied["error"])
        # A non-claimant without agent context keeps legacy behaviour.
        legacy = activity.update_action(self.conn, self.action_id, "in_progress")
        self.assertTrue(legacy["ok"])

    def test_invalid_status_rejected(self):
        result = activity.update_action(self.conn, self.action_id, "bogus")
        self.assertFalse(result["ok"])
        self.assertIn("invalid status", result["error"])

    def test_context_injects_claimed_and_in_progress(self):
        activity.claim_action(self.conn, self.action_id, "writer", novel_id=1)
        activity.update_action(self.conn, self.action_id, "in_progress", agent="writer")
        snap = agent_context.build_context_snapshot(self.conn, "writer", novel_id=1)
        self.assertIn("我的待办行动项", snap)
        self.assertIn("规则台账模板", snap)
        self.assertIn("in_progress", snap)

    def test_list_actions_accepts_status_tuple(self):
        rows = activity.list_actions(
            self.conn, status=("pending", "claimed"), limit=10
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.action_id)

    def test_due_date_helper(self):
        self.assertEqual(
            activity._due_date("3天内"),
            (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
        )
        self.assertEqual(
            activity._due_date("下周会前"),
            (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
        )
        self.assertEqual(activity._due_date("尽快"), "")

    def test_post_meeting_actions_carry_assignee_and_due(self):
        def fake_chat(model, system, user, temperature=0.3, max_tokens=900, **kwargs):
            return {
                "text": '[{"task": "整理规则台账 v2", "due": "3天内"}]',
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                "model": "mock",
            }

        report = {"action_items": [], "discussion_summary": "会议结论"}
        with mock.patch(
            "novel_editorial.services.activity.chat_deepseek", side_effect=fake_chat
        ):
            result = activity.generate_post_meeting_actions(
                self.conn, session_id=1, meeting_id=1, novel_id=1,
                attendees=["writer"], report=report, transcript=[],
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["created"], 1)
        row = self.conn.execute(
            "SELECT assignee, due_at, status FROM agent_actions "
            "WHERE task='整理规则台账 v2'"
        ).fetchone()
        self.assertEqual(row["assignee"], "writer")
        self.assertEqual(row["due_at"], (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"))
        self.assertEqual(row["status"], "pending")

    def test_auto_fill_settles_claimed_and_in_progress(self):
        activity.claim_action(self.conn, self.action_id, "writer", novel_id=1)
        activity.update_action(self.conn, self.action_id, "in_progress", agent="writer")
        self.conn.execute(
            "INSERT INTO agent_activity(agent,novel_id,activity_type,title,detail,created_at) "
            "VALUES('writer',1,'chapter','写稿','{}',datetime('now','localtime'))"
        )
        self.conn.commit()
        with mock.patch(
            "tools.auto_fill_actions.rules_decide",
            return_value=("done", "证据：本周完成"),
        ):
            result = auto_fill_actions.run(
                self.db_path, novel_id=1, days=1, use_llm=False
            )
        self.assertEqual(result["checked"], 1)
        self.assertEqual(len(result["done"]), 1)
        row = self.conn.execute(
            "SELECT status FROM agent_actions WHERE id=?", (self.action_id,)
        ).fetchone()
        self.assertEqual(row["status"], "done")

    def test_claim_and_status_audited(self):
        activity.claim_action(self.conn, self.action_id, "writer", novel_id=1)
        activity.update_action(self.conn, self.action_id, "in_progress", agent="writer")
        claimed = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE category='agent' "
            "AND action='action_claimed'"
        ).fetchone()["c"]
        self.assertGreaterEqual(claimed, 1)
        status = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE category='agent' "
            "AND action='action_status'"
        ).fetchone()["c"]
        self.assertGreaterEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
