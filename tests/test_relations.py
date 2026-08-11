"""S7 tests: relationship events, clamping, decay and integrations."""

import os
import tempfile
import unittest

from novel_pipeline import db
from tools import promises, relations


class RelationsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))

    def tearDown(self):
        self.conn.close()

    def test_ensure_creates_and_is_idempotent(self):
        r1 = relations.ensure(self.conn, "writer", "reviewer", novel_id=1)
        self.assertTrue(r1["ok"])
        r2 = relations.ensure(self.conn, "writer", "reviewer", novel_id=1)
        self.assertEqual(r1["relation"]["id"], r2["relation"]["id"])
        n = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_relations WHERE agent='writer' AND other='reviewer'"
        ).fetchone()["c"]
        self.assertEqual(n, 1)

    def test_event_deltas(self):
        relations.apply_event(self.conn, "writer", "reviewer", "feedback_rejected", novel_id=1)
        row = relations.ensure(self.conn, "writer", "reviewer", novel_id=1)["relation"]
        self.assertAlmostEqual(row["friction"], 0.1)

        relations.apply_event(self.conn, "writer", "eic", "promise_kept", novel_id=1)
        row = relations.ensure(self.conn, "writer", "eic", novel_id=1)["relation"]
        self.assertAlmostEqual(row["trust"], 0.1)

        relations.apply_event(self.conn, "writer", "eic", "promise_broken", novel_id=1)
        row = relations.ensure(self.conn, "writer", "eic", novel_id=1)["relation"]
        self.assertAlmostEqual(row["trust"], 0.0)
        self.assertAlmostEqual(row["friction"], 0.05)

        relations.apply_event(self.conn, "editor", "writer", "collaboration", novel_id=1)
        row = relations.ensure(self.conn, "editor", "writer", novel_id=1)["relation"]
        self.assertAlmostEqual(row["familiarity"], 0.05)

        relations.apply_event(self.conn, "planner", "eic", "proposal_accepted", novel_id=1)
        row = relations.ensure(self.conn, "planner", "eic", novel_id=1)["relation"]
        self.assertAlmostEqual(row["trust"], 0.1)

    def test_values_clamped(self):
        for _ in range(20):
            relations.apply_event(self.conn, "writer", "reviewer", "feedback_rejected", novel_id=1)
        row = relations.ensure(self.conn, "writer", "reviewer", novel_id=1)["relation"]
        self.assertEqual(row["friction"], 1.0)
        for _ in range(20):
            relations.apply_event(self.conn, "writer", "eic", "promise_broken", novel_id=1)
        row = relations.ensure(self.conn, "writer", "eic", novel_id=1)["relation"]
        self.assertEqual(row["trust"], 0.0)

    def test_unknown_event_rejected(self):
        result = relations.apply_event(self.conn, "writer", "reviewer", "nope", novel_id=1)
        self.assertFalse(result["ok"])

    def test_decay(self):
        self.conn.execute(
            "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
            "VALUES('writer','reviewer',1,0.5,0.5,0.5,datetime('now','localtime'))"
        )
        self.conn.commit()
        result = relations.decay(self.conn, novel_id=1)
        self.assertEqual(result["decayed"], 1)
        row = relations.ensure(self.conn, "writer", "reviewer", novel_id=1)["relation"]
        self.assertAlmostEqual(row["trust"], 0.475)
        self.assertAlmostEqual(row["friction"], 0.45)

    def test_settle_updates_relationship_with_eic(self):
        cur = self.conn.execute(
            "INSERT INTO agent_promises(agent,novel_id,promise,status,due_at,source) "
            "VALUES('writer',1,'周四前交卷纲','open','2099-01-01','test')"
        )
        self.conn.commit()
        self.conn.execute(
            "INSERT INTO agent_activity(agent,novel_id,activity_type,title,detail,created_at) "
            "VALUES('planner',1,'plan','出大纲','{}',datetime('now','localtime'))"
        )
        self.conn.commit()
        promises.settle_promises(self.conn, novel_id=1)
        row = relations.ensure(self.conn, "writer", "eic", novel_id=1)["relation"]
        self.assertGreater(row["trust"], 0.0)


if __name__ == "__main__":
    unittest.main()
