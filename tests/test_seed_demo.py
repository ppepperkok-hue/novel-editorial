import os
import tempfile
import unittest

from novel_editorial import db
from novel_editorial.seed_demo import seed


class SeedDemoTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(tmpdir, "test.db"))

    def test_seed_creates_expected_rows(self):
        seed(self.conn, chapters=5, published=2, reviewed=2)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM novels").fetchone()["c"], 1
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM chapters").fetchone()["c"], 5
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM quality_reports").fetchone()["c"], 4
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) c FROM publish_logs").fetchone()["c"], 2
        )
        statuses = [r["status"] for r in
                    self.conn.execute("SELECT status FROM chapters ORDER BY seq")]
        self.assertEqual(statuses, ["published", "published", "reviewed", "reviewed", "draft"])


if __name__ == "__main__":
    unittest.main()
