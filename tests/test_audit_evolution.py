import json
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from novel_pipeline.services import audit, ending  # noqa: E402


def make_db():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,volume_goal) "
        "VALUES('测试书','都市','测试','publishing','一卷')"
    )
    conn.execute(
        "INSERT INTO chapters(novel_id,seq,outline,status,title,words,score,published_at) "
        "VALUES(1,1,'纲','published','第一章',2000,85,'2026-08-10 10:00:00')"
    )
    conn.commit()
    return path


class AuditTests(unittest.TestCase):
    def test_log_and_list(self):
        path = make_db()
        conn = db.connect(path)
        try:
            audit.log(conn, "settings", "save_settings", detail={"a": 1})
            audit.log(conn, "operation", "run_now", target_type="workflow", target_id="daily")
            rows = audit.list_logs(conn)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["category"], "operation")
            self.assertEqual(rows[1]["detail"], {"a": 1})
            rows_filtered = audit.list_logs(conn, category="settings")
            self.assertEqual(len(rows_filtered), 1)
        finally:
            conn.close()


class EvolutionTests(unittest.TestCase):
    def test_record_work_writes_evolution(self):
        path = make_db()
        from tools import record_work

        conn = db.connect(path)
        try:
            record_work._upsert_summary(
                conn,
                1,
                1,
                1,
                {
                    "summary": {"summary": "主角变强", "character_updates": {"主角": {"changes": "觉醒血脉，性格更果断", "arc": "觉醒"}}},
                    "ending_excerpt": "",
                },
            )
            rows = conn.execute("SELECT * FROM character_evolution").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "主角")
            self.assertIn("觉醒血脉", rows[0]["change_log"])
            char = conn.execute("SELECT state FROM characters WHERE name='主角'").fetchone()
            self.assertIn("觉醒血脉", char["state"])
        finally:
            conn.close()

    def test_apply_report_character_updates(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            conn.execute(
                "UPDATE novels SET outline=? WHERE id=1",
                (
                    json.dumps(
                        {
                            "bible": {
                                "characters": [
                                    {"name": "主角", "personality": "旧", "current_state": "弱"}
                                ]
                            }
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()
            r = apply_architect.apply_report(
                conn,
                1,
                {
                    "decisions": {
                        "character_updates": [
                            {"name": "主角", "personality": "新", "current_state": "强", "goals": "复仇"}
                        ]
                    }
                },
            )
            self.assertTrue(r["ok"])
            outline = json.loads(conn.execute("SELECT outline FROM novels WHERE id=1").fetchone()["outline"])
            c = outline["bible"]["characters"][0]
            self.assertEqual(c["personality"], "新")
            self.assertEqual(c["current_state"], "强")
        finally:
            conn.close()

    def test_apply_report_cover_prompt(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            r = apply_architect.apply_report(
                conn, 1, {"cover_prompt": "热血玄幻封面", "decisions": {}}
            )
            self.assertTrue(r["ok"])
            self.assertTrue(r["cover_prompt"])
            row = conn.execute("SELECT cover_prompt FROM novels WHERE id=1").fetchone()
            self.assertEqual(row["cover_prompt"], "热血玄幻封面")

            # empty cover_prompt must not wipe the stored one
            r2 = apply_architect.apply_report(conn, 1, {"decisions": {}})
            self.assertTrue(r2["ok"])
            row = conn.execute("SELECT cover_prompt FROM novels WHERE id=1").fetchone()
            self.assertEqual(row["cover_prompt"], "热血玄幻封面")

            # next-book creation carries the cover prompt
            conn.execute("UPDATE novels SET status='finished' WHERE id=1")
            conn.commit()
            r3 = apply_architect.apply_report(
                conn,
                1,
                {
                    "cover_prompt": "新书封面：星际少女",
                    "decisions": {
                        "next_book": {
                            "book_name": "下一本",
                            "genre": "科幻",
                            "abstract": "星际冒险",
                            "selling_point": "爽",
                            "protagonist": "星",
                        }
                    },
                },
            )
            self.assertTrue(r3["ok"])
            self.assertTrue(r3["next_book_created"])
            row = conn.execute(
                "SELECT cover_prompt, status FROM novels WHERE title='下一本'"
            ).fetchone()
            self.assertEqual(row["cover_prompt"], "新书封面：星际少女")
            self.assertEqual(row["status"], "planning")
        finally:
            conn.close()


class EndingBindTests(unittest.TestCase):
    def test_bind_book_updates_env(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO novels(title,genre,premise,status) VALUES('下一本','玄幻','x','planning')"
            )
            conn.commit()
            ending.confirm_next_book(conn, 2)
            tmp_env = Path(tempfile.mkdtemp()) / ".env"
            tmp_env.write_text("FANQIE_BOOK_ID=old\nFANQIE_VOLUME_ID=v1\n", encoding="utf-8")
            with mock.patch("novel_pipeline.services.ending.config.N8N_ENV_FILE", tmp_env):
                r = ending.bind_book(conn, 2, "newbook", "v2")
            self.assertTrue(r["ok"])
            content = tmp_env.read_text(encoding="utf-8")
            self.assertIn("FANQIE_BOOK_ID=newbook", content)
            self.assertIn("FANQIE_VOLUME_ID=v2", content)
            row = conn.execute("SELECT status, book_id FROM novels WHERE id=2").fetchone()
            self.assertEqual(row["status"], "publishing")
            self.assertEqual(row["book_id"], "newbook")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
