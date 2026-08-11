"""R4-2 tests: meeting kinds and per-kind materials."""

import os
import tempfile
import unittest

from novel_editorial import db
from novel_editorial.services import meeting_session
from tools import meeting_kinds, meeting_materials


def _seed(conn):
    cur = conn.execute(
        "INSERT INTO novels(title,genre,premise,selling_point,platform,status,book_id,"
        "tags,abstract,protagonists,outline,volume_goal,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "旧书店", "都市", "主角经营旧书店", "", "fanqie", "publishing", "b1",
            "[]", "测试书", "[]",
            '{"bible": {}, "blueprints": []}', "第一卷", "2026-08-11 00:00:00",
        ),
    )
    conn.commit()
    return cur.lastrowid


class MeetingKindsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))
        self.novel_id = _seed(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_kind_registry_has_nine_kinds(self):
        self.assertEqual(len(meeting_kinds.MEETING_KINDS), 9)
        for name in (
            "weekly", "topic", "planning", "critique", "retro",
            "review", "incident", "learning", "free",
        ):
            self.assertIn(name, meeting_kinds.MEETING_KINDS)
            spec = meeting_kinds.MEETING_KINDS[name]
            self.assertTrue(spec["label"])
            self.assertTrue(spec["agenda_label"])
            self.assertTrue(spec["post_actions"])

    def test_create_session_accepts_kind(self):
        r = meeting_session.create_session(
            self.conn, "复盘昨天的失败", novel_id=self.novel_id, kind="incident"
        )
        self.assertTrue(r["ok"])
        s = meeting_session.get_session(self.conn, r["session_id"])
        self.assertEqual(s["kind"], "incident")

    def test_create_session_rejects_unknown_kind(self):
        r = meeting_session.create_session(
            self.conn, "x", novel_id=self.novel_id, kind="banquet"
        )
        self.assertFalse(r["ok"])

    def test_incident_materials_include_failures(self):
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,started_at,created_at) "
            "VALUES('r1',?,'manual','scheduler','failed',datetime('now','localtime'),datetime('now','localtime'))",
            (self.novel_id,),
        )
        self.conn.commit()
        m = meeting_materials.build_materials(
            self.conn, self.novel_id, kind="incident"
        )
        self.assertIsNotNone(m)
        self.assertEqual(len(m["context"]["failure_runs"]), 1)
        self.assertEqual(m["context"]["failure_runs"][0]["status"], "failed")

    def test_free_materials_include_topic_pool(self):
        from tools import mailroom  # noqa: E402

        mailroom.send(
            self.conn, "guard", "eic", "规则台账模板需要统一",
            kind="topic_request", novel_id=self.novel_id,
        )
        m = meeting_materials.build_materials(self.conn, self.novel_id, kind="free")
        self.assertEqual(len(m["context"]["topic_pool"]), 1)
        self.assertEqual(m["context"]["topic_pool"][0]["from_agent"], "guard")

    def test_review_materials_include_finish_metrics(self):
        m = meeting_materials.build_materials(self.conn, self.novel_id, kind="review")
        self.assertIn("finish_metrics", m["context"])
        self.assertEqual(m["context"]["finish_metrics"]["published"], 0)

    def test_learning_materials_include_drafts(self):
        m = meeting_materials.build_materials(self.conn, self.novel_id, kind="learning")
        self.assertIn("knowledge_drafts", m["context"])
        self.assertEqual(m["context"]["knowledge_drafts"], [])
