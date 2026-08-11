import os
import tempfile
import unittest

from novel_editorial import db


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "test.db"))

    def test_full_flow(self):
        nid = db.add_novel(self.conn, "测试书", "都市", "一句简介")
        vid = db.add_volume(self.conn, nid, 1, "第一卷")
        cid = db.add_chapter(self.conn, nid, vid, 1, "第1章")
        db.update_chapter_after_review(self.conn, cid, 1234, 8.5, True)
        db.add_quality_report(self.conn, cid, {"words": 10}, True)
        db.add_publish_log(self.conn, cid, "fanqie", "publish", "ok", ai_declared=1)

        row = self.conn.execute("SELECT * FROM chapters WHERE id=?", (cid,)).fetchone()
        self.assertEqual(row["status"], "reviewed")
        self.assertEqual(row["words"], 1234)

        logs = self.conn.execute("SELECT COUNT(*) c FROM publish_logs").fetchone()["c"]
        self.assertEqual(logs, 1)


if __name__ == "__main__":
    unittest.main()
