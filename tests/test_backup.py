import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from novel_pipeline.backup import backup_db


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.db_path = self.tmpdir / "novel.db"
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO t(name) VALUES ('内容A')")
        conn.commit()
        conn.close()
        self.backup_dir = self.tmpdir / "backups"

    def test_backup_creates_copy_and_keeps_content(self):
        target = backup_db(self.db_path, self.backup_dir, keep=3)
        self.assertTrue(Path(target).exists())
        conn = sqlite3.connect(target)
        name = conn.execute("SELECT name FROM t WHERE id=1").fetchone()[0]
        conn.close()
        self.assertEqual(name, "内容A")

    def test_backup_keeps_only_latest_n(self):
        for _ in range(4):
            backup_db(self.db_path, self.backup_dir, keep=3)
        backups = list(self.backup_dir.glob("novel_*.db"))
        self.assertEqual(len(backups), 3)


if __name__ == "__main__":
    unittest.main()
