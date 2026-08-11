"""R4-2 tests: post-meeting action routing per kind."""

import os
import tempfile
import unittest

from novel_pipeline import db
from tools import meeting_actions


class MeetingActionsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))

    def tearDown(self):
        self.conn.close()

    def test_incident_lessons_become_drafts(self):
        report = {
            "lessons": [
                {"title": "锁失效教训", "lesson": "断电后锁必须可回收，否则会卡死下次开工"},
                "第二次发布前必须校验章节字数",
            ]
        }
        r = meeting_actions.run_post_actions(
            self.conn, 1, 2, 0, "incident", report
        )
        self.assertTrue(r["ok"])
        self.assertEqual(r["results"]["lesson_drafts"], 2)
        rows = self.conn.execute(
            "SELECT title, status FROM knowledge_drafts"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["status"], "draft")

    def test_learning_proposals_become_drafts(self):
        report = {"proposals": ["把伏笔台账做成固定模板", "开篇钩子每卷换一种结构"]}
        r = meeting_actions.run_post_actions(
            self.conn, 3, 4, 0, "learning", report
        )
        self.assertEqual(r["results"]["knowledge_drafts"], 2)
        n = self.conn.execute("SELECT COUNT(*) c FROM knowledge_drafts").fetchone()["c"]
        self.assertEqual(n, 2)

    def test_review_records_marker(self):
        report = {"recommendation": "伏笔回收过半，建议 30 章内收尾"}
        r = meeting_actions.run_post_actions(
            self.conn, 5, 6, 0, "review", report
        )
        self.assertTrue(r["results"]["review"])
        row = self.conn.execute(
            "SELECT action FROM audit_logs WHERE action='ending_review_recorded'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_repeat_application_is_skipped(self):
        report = {"lessons": ["一次教训"]}
        meeting_actions.run_post_actions(self.conn, 7, 8, 0, "incident", report)
        r2 = meeting_actions.run_post_actions(self.conn, 7, 8, 0, "incident", report)
        self.assertTrue(r2["skipped"])
        n = self.conn.execute("SELECT COUNT(*) c FROM knowledge_drafts").fetchone()["c"]
        self.assertEqual(n, 1)
