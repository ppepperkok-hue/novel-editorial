"""S6 tests: promise recording, evidence building and settlement."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from tools import promises, write_diaries


class PromiseTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))

    def tearDown(self):
        self.conn.close()

    def _add_promise(self, text, due_at="", status="open"):
        cur = self.conn.execute(
            "INSERT INTO agent_promises(agent,novel_id,promise,status,due_at,source) "
            "VALUES('writer',1,?,?,?,'test')",
            (text, status, due_at),
        )
        self.conn.commit()
        return cur.lastrowid

    def test_record_promises_dedupes(self):
        r1 = promises.record_promises(
            self.conn, "writer", 1,
            [{"promise": "周四前交卷纲", "due_at": "2026-08-15"}],
            source="weekly",
        )
        self.assertEqual(r1["added"], 1)
        r2 = promises.record_promises(
            self.conn, "writer", 1,
            [{"promise": "周四前交卷纲", "due_at": "2026-08-16"}],
            source="weekly",
        )
        self.assertEqual(r2["added"], 0, "same open promise must not duplicate")
        n = self.conn.execute("SELECT COUNT(*) c FROM agent_promises").fetchone()["c"]
        self.assertEqual(n, 1)

    def test_settle_keeps_promise_with_plan_evidence(self):
        self._add_promise("周四前交卷纲", due_at="2099-01-01")
        self.conn.execute(
            "INSERT INTO agent_activity(agent,novel_id,activity_type,title,detail,created_at) "
            "VALUES('planner',1,'plan','出大纲','{}',datetime('now','localtime'))"
        )
        self.conn.commit()
        result = promises.settle_promises(self.conn, novel_id=1)
        self.assertEqual(len(result["kept"]), 1)
        row = self.conn.execute(
            "SELECT status FROM agent_promises WHERE promise='周四前交卷纲'"
        ).fetchone()
        self.assertEqual(row["status"], "kept")

    def test_settle_keeps_review_promise(self):
        self._add_promise("通读检查第三章", due_at="2099-01-01")
        self.conn.execute(
            "INSERT INTO agent_activity(agent,novel_id,activity_type,title,detail,created_at) "
            "VALUES('reviewer',1,'review','审稿','{}',datetime('now','localtime'))"
        )
        self.conn.commit()
        result = promises.settle_promises(self.conn, novel_id=1)
        self.assertEqual(len(result["kept"]), 1)

    def test_settle_broken_when_overdue_without_evidence(self):
        self._add_promise("周五交封面", due_at="2020-01-01")
        result = promises.settle_promises(self.conn, novel_id=1)
        self.assertEqual(len(result["broken"]), 1)
        row = self.conn.execute(
            "SELECT status FROM agent_promises WHERE promise='周五交封面'"
        ).fetchone()
        self.assertEqual(row["status"], "broken")

    def test_settle_keeps_open_without_due_or_evidence(self):
        self._add_promise("下周尝试新钩子写法", due_at="")
        result = promises.settle_promises(self.conn, novel_id=1)
        self.assertEqual(result["kept"], [])
        self.assertEqual(result["broken"], [])
        self.assertEqual(result["open"], 1)

    def test_settle_matches_action_text(self):
        pid = self._add_promise("把规则台账模板定死", due_at="")
        self.conn.execute(
            "INSERT INTO agent_actions(agent,novel_id,task,status,completed_at) "
            "VALUES('writer',1,'把规则台账模板定死','done',datetime('now','localtime'))"
        )
        self.conn.commit()
        result = promises.settle_promises(self.conn, novel_id=1)
        self.assertIn(pid, result["kept"])

    def test_weekly_diary_extracts_promises(self):
        def fake_chat(model, system, user, temperature=0.6, max_tokens=1200, **kwargs):
            return {
                "text": json.dumps(
                    {
                        "week_summary": "本周写了三章",
                        "mood": {"satisfaction": 0.6, "concern": 0.2, "excitement": 0.5, "fatigue": 0.3, "note": ""},
                        "promises": [{"promise": "下周交卷纲", "due_at": "2026-08-20"}],
                    }
                ),
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
                "model": "mock",
            }

        with mock.patch("tools.write_diaries.chat_deepseek", side_effect=fake_chat):
            write_diaries.write(self.conn, 1, "weekly", dry_run=False)
        row = self.conn.execute(
            "SELECT promise, source FROM agent_promises WHERE agent='writer'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["promise"], "下周交卷纲")
        self.assertEqual(row["source"], "weekly")
        settle = self.conn.execute(
            "SELECT COUNT(*) c FROM agent_activity WHERE activity_type='promise_settle'"
        ).fetchone()["c"]
        self.assertEqual(settle, 1)


if __name__ == "__main__":
    unittest.main()
