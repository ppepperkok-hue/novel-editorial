"""Tests for the one-shot knowledge cleanup tool."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_editorial import db  # noqa: E402
from tools import clean_novel_knowledge  # noqa: E402


def make_db():
    conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    nid = db.add_novel(conn, "测试书", "都市", "简介")
    return conn, nid


class CleanKnowledgeTests(unittest.TestCase):
    def test_merge_history_keeps_missing_drop_safe(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "world_rule", "保留行", "内容"),
            )
            conn.execute(
                "INSERT INTO novel_knowledge_history(knowledge_id,content,version,created_at) "
                "VALUES(1,'旧','1','2026-01-01 00:00:00')"
            )
            conn.commit()
            clean_novel_knowledge._merge_history(conn, 999, 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM novel_knowledge").fetchone()["c"],
                0,
            )
        finally:
            conn.close()

    def test_apply_clean_deletes_with_history(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "world_rule", "金手指重复", "内容"),
            )
            conn.execute(
                "INSERT INTO novel_knowledge_history(knowledge_id,content,version,created_at) "
                "VALUES(1,'旧','1','2026-01-01 00:00:00')"
            )
            conn.commit()
            clean_novel_knowledge.apply_clean(
                conn,
                {
                    "renames": [],
                    "state_rows": [],
                    "golden_finger_dups": [{"keep_id": None, "id": 1}],
                    "similar_rules": [],
                    "misclassified": [],
                },
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) c FROM novel_knowledge").fetchone()["c"],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) c FROM novel_knowledge_history"
                ).fetchone()["c"],
                0,
            )
        finally:
            conn.close()

    def test_plan_renames_sentence_entities(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "world_rule", "三香引魂：殡葬师以三炷香为号，一香问路", "规则内容"),
            )
            conn.commit()
            plan = clean_novel_knowledge.plan_clean(conn)
            self.assertEqual(len(plan["renames"]), 1)
            self.assertEqual(plan["renames"][0]["to"], "三香引魂")
        finally:
            conn.close()

    def test_plan_merges_state_rows(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "character", "苏晚晴", "角色卡"),
            )
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "character", "苏晚晴·状态", "筑基中期"),
            )
            conn.commit()
            plan = clean_novel_knowledge.plan_clean(conn)
            self.assertEqual(len(plan["state_rows"]), 1)
            self.assertEqual(plan["state_rows"][0]["to"], "苏晚晴")
            clean_novel_knowledge.apply_clean(conn, plan)
            rows = conn.execute(
                "SELECT entity FROM novel_knowledge WHERE novel_id=? AND category='character'",
                (nid,),
            ).fetchall()
            self.assertEqual([r["entity"] for r in rows], ["苏晚晴"])
        finally:
            conn.close()

    def test_plan_drops_duplicate_golden_finger(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "item", "金手指", "能力说明"),
            )
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "power", "金手指", "能力说明"),
            )
            conn.commit()
            plan = clean_novel_knowledge.plan_clean(conn)
            self.assertEqual(len(plan["golden_finger_dups"]), 1)
            clean_novel_knowledge.apply_clean(conn, plan)
            rows = conn.execute(
                "SELECT category FROM novel_knowledge WHERE novel_id=? AND entity='金手指'",
                (nid,),
            ).fetchall()
            self.assertEqual([r["category"] for r in rows], ["item"])
        finally:
            conn.close()

    def test_plan_merges_similar_rules(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,2,'2026-01-01 00:00:00')",
                (nid, "world_rule", "阴阳守恒", "规则一"),
            )
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "world_rule", "阴阳守恒之律", "规则一"),
            )
            conn.commit()
            plan = clean_novel_knowledge.plan_clean(conn)
            self.assertEqual(len(plan["similar_rules"]), 1)
            item = plan["similar_rules"][0]
            self.assertEqual(item["keep_entity"], "阴阳守恒")
            clean_novel_knowledge.apply_clean(conn, plan)
            rows = conn.execute(
                "SELECT entity FROM novel_knowledge WHERE novel_id=? AND category='world_rule'",
                (nid,),
            ).fetchall()
            self.assertEqual([r["entity"] for r in rows], ["阴阳守恒"])
        finally:
            conn.close()

    def test_plan_drops_misclassified_rows(self):
        conn, nid = make_db()
        try:
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "plot", "人物关系", "旧格式"),
            )
            conn.execute(
                "INSERT INTO novel_knowledge(novel_id,category,entity,content,version,updated_at) "
                "VALUES(?,?,?,?,1,'2026-01-01 00:00:00')",
                (nid, "world_rule", "文风", "旧格式"),
            )
            conn.commit()
            plan = clean_novel_knowledge.plan_clean(conn)
            self.assertEqual(len(plan["misclassified"]), 2)
            clean_novel_knowledge.apply_clean(conn, plan)
            rows = conn.execute(
                "SELECT COUNT(*) c FROM novel_knowledge WHERE novel_id=?",
                (nid,),
            ).fetchone()["c"]
            self.assertEqual(rows, 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
