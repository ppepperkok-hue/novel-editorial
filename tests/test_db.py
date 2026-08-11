import os
import sqlite3
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

    def test_legacy_schema_migrates_relations_and_messages(self):
        path = os.path.join(self.tmpdir, "legacy.db")
        raw = sqlite3.connect(path)
        raw.executescript(
            """
            CREATE TABLE agent_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                other_agent TEXT NOT NULL,
                novel_id INTEGER DEFAULT 0,
                familiarity REAL DEFAULT 0,
                trust REAL DEFAULT 0,
                friction REAL DEFAULT 0,
                notes TEXT DEFAULT '',
                updated_at TEXT DEFAULT ''
            );
            CREATE TABLE agent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_agent TEXT NOT NULL,
                to_agent TEXT NOT NULL,
                kind TEXT DEFAULT 'note',
                subject TEXT DEFAULT '',
                body TEXT NOT NULL,
                ref_novel_id INTEGER DEFAULT 0,
                ref_chapter_id INTEGER DEFAULT 0,
                reply_to INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'unread',
                created_at TEXT DEFAULT '',
                read_at TEXT DEFAULT '',
                resolved_at TEXT DEFAULT ''
            );
            INSERT INTO agent_relations(agent, other_agent, novel_id)
            VALUES('writer','eic',1);
            INSERT INTO agent_messages(from_agent,to_agent,body)
            VALUES('eic','writer','x');
            """
        )
        raw.commit()
        raw.close()

        migrated = db.connect(path)
        try:
            rel_cols = [
                r["name"]
                for r in migrated.execute("PRAGMA table_info(agent_relations)")
            ]
            self.assertIn("other", rel_cols)
            row = migrated.execute(
                "SELECT other FROM agent_relations WHERE agent='writer'"
            ).fetchone()
            self.assertEqual(row["other"], "eic")
            msg_cols = [
                r["name"]
                for r in migrated.execute("PRAGMA table_info(agent_messages)")
            ]
            self.assertIn("resolution", msg_cols)

            from tools import mailroom, relations  # noqa: E402

            self.assertTrue(relations.ensure(migrated, "writer", "eic", 1)["ok"])
            msgs = mailroom.list_messages(migrated, agent="writer")["messages"]
            self.assertTrue(msgs)
            self.assertTrue(mailroom.resolve(migrated, msgs[0]["id"], "rework")["ok"])
        finally:
            migrated.close()


if __name__ == "__main__":
    unittest.main()
