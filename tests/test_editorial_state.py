"""S5 tests: read-side editorial state queries."""

import os
import tempfile
import unittest

from novel_pipeline import db
from tools import editorial_state


class EditorialStateTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))
        self.conn.execute(
            "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
            "VALUES('writer','reviewer',1,0.2,0.3,0.4,datetime('now','localtime'))"
        )
        self.conn.execute(
            "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
            "VALUES('writer',1,'collaboration',0.9,'被打回过','review',datetime('now','localtime'))"
        )
        self.conn.execute(
            "INSERT INTO agent_promises(agent,novel_id,promise,status,due_at,source) "
            "VALUES('writer',1,'周四交卷纲','open','2026-08-15','weekly')"
        )
        self.conn.execute(
            "INSERT INTO agent_promises(agent,novel_id,promise,status,due_at,source) "
            "VALUES('writer',1,'周五交封面','kept','2026-08-16','weekly')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_relations_filtered_and_scoped(self):
        result = editorial_state.list_relations(self.conn, agent="writer", novel_id=1)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["other"], "reviewer")
        result2 = editorial_state.list_relations(self.conn, agent="memory", novel_id=1)
        self.assertEqual(result2["items"], [])

    def test_memories_category_filter(self):
        result = editorial_state.list_memories(
            self.conn, agent="writer", novel_id=1, category="collaboration"
        )
        self.assertEqual(len(result["items"]), 1)
        result2 = editorial_state.list_memories(
            self.conn, agent="writer", novel_id=1, category="nope"
        )
        self.assertEqual(result2["items"], [])

    def test_promises_status_filter(self):
        result = editorial_state.list_promises(
            self.conn, agent="writer", novel_id=1, status="open"
        )
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["promise"], "周四交卷纲")
        all_result = editorial_state.list_promises(self.conn, agent="writer", novel_id=1)
        self.assertEqual(len(all_result["items"]), 2)

    def test_limit_clamped(self):
        result = editorial_state.list_memories(self.conn, agent="writer", limit=99999)
        self.assertLessEqual(len(result["items"]), 500)


if __name__ == "__main__":
    unittest.main()
