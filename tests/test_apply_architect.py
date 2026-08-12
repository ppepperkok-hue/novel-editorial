"""Direct unit tests for tools/apply_architect.py (R12-E-03)."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_editorial import db  # noqa: E402
from tools import apply_architect  # noqa: E402


def _make_db():
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,volume_goal) "
        "VALUES('测试书','都市','测试','publishing','一卷')"
    )
    conn.commit()
    conn.close()
    return path


class MergeBlueprintsTests(unittest.TestCase):
    def test_merge_blueprints_tolerates_missing_inputs(self):
        self.assertEqual(apply_architect.merge_blueprints(None, None), [])
        self.assertEqual(apply_architect.merge_blueprints(None, []), [])
        self.assertEqual(apply_architect.merge_blueprints([], []), [])

    def test_merge_blueprints_keeps_non_numeric_seq_without_crash(self):
        merged = apply_architect.merge_blueprints(
            [{"seq": "abc", "title": "旧"}],
            [{"seq": None, "title": "新"}],
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual([b["seq"] for b in merged], [1, 2])
        self.assertEqual(merged[0]["title"], "旧")
        self.assertEqual(merged[1]["title"], "新")

    def test_merge_blueprints_updates_by_seq_and_sorts(self):
        merged = apply_architect.merge_blueprints(
            [{"seq": 1, "title": "一"}, {"seq": 3, "title": "三"}],
            [{"seq": 3, "title": "三改"}, {"seq": 2, "title": "二"}],
        )
        self.assertEqual([b["seq"] for b in merged], [1, 2, 3])
        self.assertEqual(merged[1]["title"], "二")
        self.assertEqual(merged[2]["title"], "三改")


class ApplyReportIdempotencyTests(unittest.TestCase):
    def test_apply_report_blueprint_merge_is_idempotent(self):
        path = _make_db()
        conn = db.connect(path)
        try:
            report = {
                "decisions": {
                    "blueprint_updates": [
                        {"seq": 2, "title": "第二章", "outline": "大纲", "hook": "钩子"}
                    ]
                }
            }
            r1 = apply_architect.apply_report(conn, 1, report)
            r2 = apply_architect.apply_report(conn, 1, report)
            self.assertTrue(r1["ok"])
            self.assertEqual(r1["blueprints"], 1)
            self.assertEqual(r2["blueprints"], 1)
            outline = json.loads(
                conn.execute("SELECT outline FROM novels WHERE id=1").fetchone()["outline"]
            )
            self.assertEqual(len(outline["blueprints"]), 1)
        finally:
            conn.close()

    def test_apply_report_character_updates_are_idempotent(self):
        path = _make_db()
        conn = db.connect(path)
        try:
            report = {
                "decisions": {
                    "character_updates": [
                        {"name": "林舟", "change_log": "同一份周会结论"}
                    ]
                }
            }
            apply_architect.apply_report(conn, 1, report)
            apply_architect.apply_report(conn, 1, report)
            count = conn.execute(
                "SELECT COUNT(*) c FROM character_evolution "
                "WHERE novel_id=1 AND change_log='同一份周会结论'"
            ).fetchone()["c"]
            self.assertEqual(count, 1, "identical weekly change must not duplicate")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
