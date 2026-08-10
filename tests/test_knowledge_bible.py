"""Tests for story-bible initialization into the per-novel knowledge store."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from tools import novel_knowledge  # noqa: E402


def make_db():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,outline) "
        "VALUES('书','玄幻','设定','publishing','{}')"
    )
    conn.execute("INSERT INTO volumes(novel_id,seq,goal) VALUES(1,1,'第一卷')")
    conn.commit()
    conn.close()
    return path


BIBLE = {
    "world_rules": ["灵气复苏，境界：练气-筑基-金丹", "灵根决定修炼速度"],
    "characters": [
        {"name": "林一", "role": "主角", "identity": "废灵根少年",
         "personality": "坚韧", "speech_style": "寡言", "current_state": "练气一层"},
    ],
    "relationships": [{"from": "林一", "to": "师父", "relation": "师徒"}],
    "golden_finger": "破碗可提纯灵物",
    "main_plot": "废灵根少年逆袭",
    "style_guide": "平实白描，短句为主",
}


class BibleInitTests(unittest.TestCase):
    def test_sync_from_bible_populates_categories(self):
        path = make_db()
        conn = db.connect(path)
        try:
            result = novel_knowledge.sync_from_bible(conn, 1, BIBLE)
            self.assertGreaterEqual(result["count"], 7)
            rows = novel_knowledge.get(conn, 1)
            cats = {r["category"] for r in rows}
            self.assertIn("world_rule", cats)
            self.assertIn("character", cats)
            self.assertIn("plot", cats)
            self.assertIn("item", cats)
            self.assertIn("power", cats)
            char = conn.execute(
                "SELECT content FROM novel_knowledge "
                "WHERE novel_id=1 AND category='character' AND entity='林一'"
            ).fetchone()
            self.assertIn("练气一层", char["content"])
            self.assertIn("personality: 坚韧", char["content"])
        finally:
            conn.close()

    def test_sync_is_idempotent(self):
        path = make_db()
        conn = db.connect(path)
        try:
            novel_knowledge.sync_from_bible(conn, 1, BIBLE)
            versions = {
                r["entity"]: r["version"]
                for r in conn.execute(
                    "SELECT entity, version FROM novel_knowledge WHERE novel_id=1"
                ).fetchall()
            }
            result = novel_knowledge.sync_from_bible(conn, 1, BIBLE)
            self.assertEqual(result["count"], 0, "unchanged bible must not re-version")
            after = {
                r["entity"]: r["version"]
                for r in conn.execute(
                    "SELECT entity, version FROM novel_knowledge WHERE novel_id=1"
                ).fetchall()
            }
            self.assertEqual(versions, after)
        finally:
            conn.close()

    def test_sync_latest_initializes_without_chapters(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "UPDATE novels SET outline=? WHERE id=1",
                (json.dumps({"bible": BIBLE}, ensure_ascii=False),),
            )
            conn.commit()
            result = novel_knowledge.sync_latest(conn)
            self.assertEqual(result["novel_id"], 1)
            self.assertGreaterEqual(result["count"], 7)
        finally:
            conn.close()


class AutopilotLockTests(unittest.TestCase):
    def test_daily_run_skips_when_lock_held(self):
        path = make_db()
        conn = db.connect(path)
        try:
            from novel_pipeline import autopilot

            with mock.patch("tools.preflight.acquire_lock", return_value=(False, "锁被占用")):
                result = autopilot.daily_run(
                    conn, None, "设定", chapters=1, chapters_per_day=1
                )
            self.assertFalse(result["ok"])
            self.assertTrue(result.get("skipped"))
            self.assertIn("锁被占用", result["reason"])
        finally:
            conn.close()


class QualityReportPersistTests(unittest.TestCase):
    def test_quality_passed_written_by_record_work(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
                "VALUES(1,1,1,'章纲','published','第 1 章')"
            )
            conn.commit()
            from tools import record_work

            record_work.upsert_chapters(
                conn,
                1,
                [{"seq": 1, "outline": "章纲", "title": "第 1 章", "status": "published",
                  "words": 2000, "quality_passed": True, "summary": {}}],
            )
            row = conn.execute(
                "SELECT passed FROM quality_reports WHERE chapter_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(row["passed"], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
