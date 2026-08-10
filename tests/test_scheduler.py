import os
import tempfile
import unittest

from novel_pipeline import db
from novel_pipeline.scheduler import Scheduler


class FakeAdapter:
    def __init__(self):
        self.calls = []

    def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
        self.calls.append(chapter_id)
        return {"result": "ok", "chapter_id": chapter_id}


class FakeSink:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "test.db"))
        self.adapter = FakeAdapter()
        self.sink = FakeSink()

    def test_tick_publishes_up_to_limit_and_marks_published(self):
        nid = db.add_novel(self.conn, "测试书", "都市", "简介")
        vid = db.add_volume(self.conn, nid, 1, "第一卷")
        chapters = [db.add_chapter(self.conn, nid, vid, seq, f"第{seq}章") for seq in (1, 2, 3)]
        for cid in chapters:
            db.update_chapter_after_review(self.conn, cid, 1000, 8.0, True)
            self.conn.execute(
                "INSERT INTO chapter_content(chapter_id,content,updated_at) "
                "VALUES(?,?,datetime('now','localtime'))",
                (cid, f"第{cid}章正文"),
            )
            self.conn.commit()

        sched = Scheduler(adapter=self.adapter, chapters_per_day=2, alert_sink=self.sink)
        report = sched.tick(self.conn)

        self.assertEqual(len(report["published"]), 2)
        self.assertEqual(len(self.adapter.calls), 2)
        statuses = [r["status"] for r in
                    self.conn.execute("SELECT status FROM chapters ORDER BY seq")]
        self.assertEqual(statuses, ["published", "published", "reviewed"])

    def test_tick_warns_when_backlog_below_safe_line(self):
        nid = db.add_novel(self.conn, "测试书", "都市", "简介")
        vid = db.add_volume(self.conn, nid, 1, "第一卷")
        cid = db.add_chapter(self.conn, nid, vid, 1, "第1章")
        db.update_chapter_after_review(self.conn, cid, 1000, 8.0, True)

        sched = Scheduler(adapter=self.adapter, safe_backlog=3, alert_sink=self.sink)
        report = sched.tick(self.conn)

        self.assertTrue(report["warnings"])
        self.assertTrue(self.sink.messages)


if __name__ == "__main__":
    unittest.main()
