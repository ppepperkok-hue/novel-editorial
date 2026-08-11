"""S8 tests: task-board columns, claiming, status machine and permissions."""

import os
import tempfile
import unittest

from novel_pipeline import db
from novel_pipeline.services import activity
from tools import agent_context


class AgentActionsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))
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


if __name__ == "__main__":
    unittest.main()
