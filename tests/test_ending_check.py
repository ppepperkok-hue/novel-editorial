"""S16 tests: weekly ending-readiness check."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from tools import ending_check


class EndingCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        cur = self.conn.execute(
            "INSERT INTO novels(title,genre,premise,selling_point,platform,status,book_id,"
            "tags,abstract,protagonists,outline,volume_goal,target_chapters,updated_at) "
            "VALUES('测试书','都市','设定','','fanqie','publishing','b1','[]','x'*60,"
            "'[]','{}','第一卷',80,datetime('now','localtime'))"
        )
        self.conn.commit()
        self.novel_id = cur.lastrowid

    def tearDown(self):
        self.conn.close()

    def _judge(self, should_finish=True, remaining=10):
        return {
            "ok": True,
            "text": json.dumps(
                {
                    "should_finish": should_finish,
                    "remaining_chapters": remaining,
                    "reasons": ["主线进入终局"],
                    "story_progress": 92,
                    "risks": ["再拖会注水"],
                }
            ),
            "model": "mock",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    def test_recommends_finishing_and_applies(self):
        with mock.patch(
            "tools.ending_check.agent_tool_loop.run", return_value=self._judge()
        ):
            result = ending_check.check(self.conn, self.novel_id, db_path=self.db_path)
        self.assertTrue(result["should_finish"])
        self.assertTrue(result["changed"])
        row = self.conn.execute(
            "SELECT status, finish_remaining, finish_note FROM novels WHERE id=?",
            (self.novel_id,),
        ).fetchone()
        self.assertEqual(row["status"], "finishing")
        self.assertEqual(row["finish_remaining"], 10)
        self.assertIn("终局", row["finish_note"])

    def test_keeps_publishing_when_not_recommended(self):
        with mock.patch(
            "tools.ending_check.agent_tool_loop.run", return_value=self._judge(False, 0)
        ):
            result = ending_check.check(self.conn, self.novel_id, db_path=self.db_path)
        self.assertFalse(result["should_finish"])
        self.assertFalse(result["changed"])
        row = self.conn.execute(
            "SELECT status FROM novels WHERE id=?", (self.novel_id,)
        ).fetchone()
        self.assertEqual(row["status"], "publishing")

    def test_judge_failure_is_explicit_and_non_mutating(self):
        with mock.patch(
            "tools.ending_check.agent_tool_loop.run",
            return_value={"ok": False, "error": "judge crashed"},
        ):
            result = ending_check.check(self.conn, self.novel_id, db_path=self.db_path)
        self.assertFalse(result["ok"])
        self.assertIn("judge crashed", result["error"])
        row = self.conn.execute(
            "SELECT status FROM novels WHERE id=?", (self.novel_id,)
        ).fetchone()
        self.assertEqual(row["status"], "publishing")

    def test_dry_run_never_mutates(self):
        with mock.patch(
            "tools.ending_check.agent_tool_loop.run", return_value=self._judge()
        ):
            result = ending_check.check(
                self.conn, self.novel_id, dry_run=True, db_path=self.db_path
            )
        self.assertTrue(result["should_finish"])
        self.assertFalse(result["changed"])
        row = self.conn.execute(
            "SELECT status FROM novels WHERE id=?", (self.novel_id,)
        ).fetchone()
        self.assertEqual(row["status"], "publishing")

    def test_no_active_novel_skips(self):
        self.conn.execute("UPDATE novels SET status='finished'")
        self.conn.commit()
        with mock.patch(
            "tools.ending_check.agent_tool_loop.run",
            side_effect=AssertionError("must not evaluate without active novel"),
        ):
            result = ending_check.check(self.conn, db_path=self.db_path)
        self.assertFalse(result["evaluated"])

    def test_finishing_book_remaining_updated(self):
        self.conn.execute(
            "UPDATE novels SET status='finishing', finish_remaining=5 WHERE id=?",
            (self.novel_id,),
        )
        self.conn.commit()
        with mock.patch(
            "tools.ending_check.agent_tool_loop.run", return_value=self._judge(True, 12)
        ):
            result = ending_check.check(self.conn, self.novel_id, db_path=self.db_path)
        self.assertTrue(result["changed"])
        row = self.conn.execute(
            "SELECT finish_remaining FROM novels WHERE id=?", (self.novel_id,)
        ).fetchone()
        self.assertEqual(row["finish_remaining"], 12)


if __name__ == "__main__":
    unittest.main()
