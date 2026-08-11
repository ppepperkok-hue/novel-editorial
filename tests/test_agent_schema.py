"""S1 schema tests: editorial-persona tables exist, migrate idempotently and
enforce their key constraints."""

import os
import sqlite3
import tempfile
import unittest

from novel_editorial import db


class AgentSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")

    def _tables(self):
        conn = db.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            return {r["name"] for r in rows}
        finally:
            conn.close()

    def test_four_new_tables_exist(self):
        tables = self._tables()
        for name in (
            "agent_messages",
            "agent_relations",
            "agent_memories",
            "agent_promises",
        ):
            self.assertIn(name, tables, name)

    def test_connect_is_idempotent(self):
        db.connect(self.db_path).close()
        db.connect(self.db_path).close()
        db.connect(self.db_path).close()
        self.assertEqual(len(self._tables()), len(self._tables()))

    def test_message_insert_and_defaults(self):
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO agent_messages(from_agent,to_agent,subject,body,"
                "ref_novel_id,created_at) VALUES(?,?,?,?,?,datetime('now','localtime'))",
                ("reviewer", "writer", "打回", "第二章逻辑有漏洞", 1),
            )
            mid = cur.lastrowid
            conn.commit()
            row = conn.execute(
                "SELECT * FROM agent_messages WHERE id=?", (mid,)
            ).fetchone()
            self.assertEqual(row["status"], "unread")
            self.assertEqual(row["kind"], "note")
            self.assertEqual(row["reply_to"], 0)
        finally:
            conn.close()

    def test_relations_unique_per_pair_and_novel(self):
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
                "VALUES('writer','reviewer',1,0.2,0.3,0.4,datetime('now','localtime'))"
            )
            conn.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
                    "VALUES('writer','reviewer',1,0.9,0.9,0.1,datetime('now','localtime'))"
                )
            # A different novel is a separate relationship row.
            conn.execute(
                "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
                "VALUES('writer','reviewer',2,0.1,0.1,0.1,datetime('now','localtime'))"
            )
            conn.commit()
            n = conn.execute("SELECT COUNT(*) c FROM agent_relations").fetchone()["c"]
            self.assertEqual(n, 2)
        finally:
            conn.close()

    def test_memory_fields(self):
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO agent_memories(agent,novel_id,category,importance,content,source,created_at) "
                "VALUES('writer',1,'collaboration',0.8,'审稿打回过我的第二章','review-feedback',"
                "datetime('now','localtime'))"
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM agent_memories WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            self.assertEqual(row["category"], "collaboration")
            self.assertAlmostEqual(row["importance"], 0.8)
        finally:
            conn.close()

    def test_promise_defaults_and_status(self):
        conn = db.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO agent_promises(agent,novel_id,promise,due_at,source) "
                "VALUES('writer',1,'周四前交卷纲','2026-08-15','weekly')"
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM agent_promises WHERE id=?", (cur.lastrowid,)
            ).fetchone()
            self.assertEqual(row["status"], "open")
            self.assertEqual(row["due_at"], "2026-08-15")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
