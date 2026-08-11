import os
import tempfile
import unittest
from pathlib import Path

from novel_editorial import db, quality_gate
from novel_editorial.backup import backup_db
from novel_editorial.pipeline import parse_review
from novel_editorial.scheduler import Scheduler


class FakeAdapter:
    def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
        return {"result": "ok"}


class HardeningTests(unittest.TestCase):
    def test_parse_review_rejects_non_json(self):
        with self.assertRaises(ValueError):
            parse_review("这段输出里没有任何 JSON")

    def test_parse_review_accepts_json_with_fence(self):
        text = "```json\n{\"passed\": true}\n```"
        self.assertEqual(parse_review(text), {"passed": True})

    def test_empty_text_fails_quality_gate(self):
        report = quality_gate.score_chapter("", ["关键词"], min_chars=100, max_chars=200)
        self.assertFalse(report["passed"])

    def test_scheduler_tick_on_empty_db_returns_empty_report(self):
        tmpdir = tempfile.mkdtemp()
        conn = db.connect(os.path.join(tmpdir, "test.db"))
        report = Scheduler(adapter=FakeAdapter()).tick(conn)
        self.assertEqual(report["published"], [])
        self.assertEqual(report["warnings"], [])

    def test_backup_missing_db_raises(self):
        tmpdir = tempfile.mkdtemp()
        with self.assertRaises(FileNotFoundError):
            backup_db(Path(tmpdir) / "not_exists.db", Path(tmpdir) / "backups")


if __name__ == "__main__":
    unittest.main()
