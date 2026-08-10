"""Tests for record_work persistence: characters, foreshadowing, costs."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from tools import record_work  # noqa: E402


def make_db():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute("INSERT INTO novels(title,genre,premise,status) VALUES('书','都市','设定','publishing')")
    conn.execute("INSERT INTO volumes(novel_id,seq,goal) VALUES(1,1,'第一卷')")
    conn.execute(
        "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
        "VALUES(1,1,1,'章纲','published','第 1 章')"
    )
    conn.execute(
        "INSERT INTO characters(novel_id,name,role,traits,goals,state,first_seen_chapter) "
        "VALUES(1,'配角A','配角','旧特征','旧目标','{}',1)"
    )
    conn.execute(
        "INSERT INTO plot_threads(novel_id,planted_chapter,expected_recover_chapter,status,description) "
        "VALUES(1,1,11,'open','玉佩的秘密')"
    )
    conn.commit()
    conn.close()
    return path


class RecordWorkTests(unittest.TestCase):
    def test_upsert_characters_keeps_supporting_cast(self):
        path = make_db()
        conn = db.connect(path)
        try:
            record_work.upsert_characters(
                conn, 1, [{"name": "主角", "role": "主角", "traits": "新", "goals": "复仇"}]
            )
            rows = conn.execute(
                "SELECT name, traits FROM characters WHERE novel_id=1 ORDER BY id"
            ).fetchall()
            names = [r["name"] for r in rows]
            self.assertIn("主角", names)
            self.assertIn("配角A", names, "supporting cast must survive the upsert")
            side = conn.execute("SELECT traits FROM characters WHERE name='配角A'").fetchone()
            self.assertEqual(side["traits"], "旧特征")
        finally:
            conn.close()

    def test_foreshadow_recover_closes_exact_thread(self):
        path = make_db()
        conn = db.connect(path)
        try:
            ch = {
                "seq": 1,
                "outline": "章纲",
                "title": "第 1 章",
                "status": "published",
                "words": 200,
                "summary": {
                    "summary": "回收伏笔",
                    "character_updates": {},
                    "plot_events": [],
                    "foreshadowing_planted": [],
                    "foreshadowing_recovered": [{"description": "玉佩的秘密"}],
                },
            }
            record_work.upsert_chapters(conn, 1, [ch])
            row = conn.execute(
                "SELECT status FROM plot_threads WHERE description='玉佩的秘密'"
            ).fetchone()
            self.assertEqual(row["status"], "closed")
        finally:
            conn.close()

    def test_cost_insert_idempotent_per_run(self):
        path = make_db()
        conn = db.connect(path)
        try:
            payload = {
                "costs": [
                    {"node": "写手A", "model": "deepseek-v4-pro",
                     "prompt_tokens": 1000, "completion_tokens": 500}
                ]
            }
            record_work.upsert_costs(conn, 1, payload, run_id="run-1")
            record_work.upsert_costs(conn, 1, payload, run_id="run-1")
            count = conn.execute(
                "SELECT COUNT(*) c FROM cost_logs WHERE run_id='run-1' AND node_name='写手A'"
            ).fetchone()["c"]
            self.assertEqual(count, 1, "same run_id must not double-count costs")
            record_work.upsert_costs(conn, 1, payload, run_id="run-2")
            count = conn.execute(
                "SELECT COUNT(*) c FROM cost_logs WHERE node_name='写手A'"
            ).fetchone()["c"]
            self.assertEqual(count, 2)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
