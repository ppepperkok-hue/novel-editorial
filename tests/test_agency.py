"""R3-1 tests: agent agency whitelist."""

import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from novel_pipeline.services import agency
from novel_pipeline.services import activity
from tools import mailroom


class AgencyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))

    def tearDown(self):
        self.conn.close()

    def test_write_report_logs_activity(self):
        r = agency.apply(
            self.conn, "guard", 1,
            [{"action": "write_report", "body": "设定冲突检查报告：第三章时间线有歧义"}],
        )
        self.assertEqual(r["applied"], 1)
        rows = self.conn.execute(
            "SELECT activity_type, title FROM agent_activity WHERE agent='guard'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["activity_type"], "agency_report")

    def test_update_draft_creates_knowledge_draft(self):
        r = agency.apply(
            self.conn, "knowledge_keeper", 1,
            [{"action": "update_draft", "title": "伏笔回收模板", "body": "每卷开头列台账"}],
        )
        self.assertEqual(r["applied"], 1)
        row = self.conn.execute(
            "SELECT title, status FROM knowledge_drafts"
        ).fetchone()
        self.assertEqual(row["title"], "伏笔回收模板")
        self.assertEqual(row["status"], "draft")

    def test_post_issue_sends_topic_request(self):
        r = agency.apply(
            self.conn, "reader", 1,
            [{"action": "post_issue", "body": "第三章钩子太弱，建议开会讨论"}],
        )
        self.assertEqual(r["applied"], 1)
        msgs = mailroom.list_messages(self.conn, agent="eic")["messages"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["kind"], "topic_request")

    def test_claim_task_claims_action(self):
        created = activity.create_action(
            self.conn, "writer", "写第三章", novel_id=1
        )
        r = agency.apply(
            self.conn, "writer", 1,
            [{"action": "claim_task", "action_id": created["id"]}],
        )
        self.assertEqual(r["applied"], 1)
        row = self.conn.execute(
            "SELECT claimed_by, status FROM agent_actions WHERE id=?",
            (created["id"],),
        ).fetchone()
        self.assertEqual(row["claimed_by"], "writer")
        self.assertEqual(row["status"], "claimed")

    def test_propose_creates_action(self):
        r = agency.apply(
            self.conn, "planner", 1,
            [{"action": "propose", "body": "下一卷加一条支线", "priority": "medium"}],
        )
        self.assertEqual(r["applied"], 1)
        row = self.conn.execute(
            "SELECT agent, task FROM agent_actions"
        ).fetchone()
        self.assertEqual(row["agent"], "planner")
        self.assertIn("支线", row["task"])

    def test_unknown_action_rejected_with_audit(self):
        r = agency.apply(
            self.conn, "writer", 1,
            [{"action": "publish_book", "body": "x"}],
        )
        self.assertEqual(r["applied"], 0)
        self.assertEqual(r["rejected"], 1)
        row = self.conn.execute(
            "SELECT action, detail FROM audit_logs WHERE category='agency'"
        ).fetchone()
        self.assertEqual(row["action"], "rejected")
        self.assertIn("publish_book", row["detail"])

    def test_disabled_returns_noop(self):
        with mock.patch("novel_pipeline.services.agency.config.AGENCY_ENABLED", False):
            r = agency.apply(
                self.conn, "writer", 1,
                [{"action": "write_report", "body": "x"}],
            )
        self.assertFalse(r["ok"])
        self.assertEqual(r["applied"], 0)
