import json
import os
import tempfile
import unittest

from novel_pipeline import db
from tools import novel_knowledge


class NovelKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
        nid = db.add_novel(self.conn, "测试书", "都市", "简介")
        self.nid = nid
        vid = db.add_volume(self.conn, nid, 1, "第一卷")
        self.cid1 = db.add_chapter(self.conn, nid, vid, 1, "第1章")
        self.cid2 = db.add_chapter(self.conn, nid, vid, 2, "第2章")

    def tearDown(self):
        self.conn.close()

    def test_upsert_versions_and_keeps_history(self):
        kid = novel_knowledge.upsert(
            self.conn, self.nid, "character", "苏晚晴",
            "筑基初期，重伤未愈", source_chapter=self.cid1,
        )
        self.assertIsNotNone(kid)
        kid2 = novel_knowledge.upsert(
            self.conn, self.nid, "character", "苏晚晴",
            "筑基中期，伤势痊愈", source_chapter=self.cid2,
            change_note="突破",
        )
        self.assertEqual(kid, kid2)
        items = novel_knowledge.get(self.conn, self.nid, category="character")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["version"], 2)
        self.assertEqual(items[0]["content"], "筑基中期，伤势痊愈")
        hist = novel_knowledge.history(self.conn, kid)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["content"], "筑基初期，重伤未愈")
        self.assertEqual(hist[0]["version"], 1)

    def test_resolve_keyword_search(self):
        novel_knowledge.upsert(self.conn, self.nid, "item", "破碗", "每日只能提纯三次灵药")
        novel_knowledge.upsert(self.conn, self.nid, "world_rule", "灵气复苏", "灵气浓度随深度增加")
        hits = novel_knowledge.resolve(self.conn, self.nid, "破碗")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["entity"], "破碗")
        hits = novel_knowledge.resolve(self.conn, self.nid, "灵气")
        self.assertEqual(len(hits), 1)

    def test_snapshot_groups_by_category(self):
        novel_knowledge.upsert(self.conn, self.nid, "character", "苏晚晴", "筑基中期")
        novel_knowledge.upsert(self.conn, self.nid, "plot", "苏晚晴被掳", "反派劫走主角")
        snap = novel_knowledge.snapshot(self.conn, self.nid)
        cats = {s["category"] for s in snap}
        self.assertIn("character", cats)
        self.assertIn("plot", cats)
        self.assertEqual(len(snap), 2)

    def test_sync_from_chapters(self):
        db.add_chapter_summary(
            self.conn, self.cid1, "第一章主角登场",
            json.dumps({"苏晚晴": {"current_state": "筑基初期，重伤"}}, ensure_ascii=False),
            json.dumps(
                [{"description": "破碗认主", "event_type": "item", "importance": 4, "resolved": False}],
                ensure_ascii=False,
            ),
        )
        db.add_chapter_summary(
            self.conn, self.cid2, "第二章突破",
            json.dumps({"苏晚晴": {"current_state": "筑基中期，痊愈"}}, ensure_ascii=False),
            "[]",
        )
        result = novel_knowledge.sync_from_chapters(self.conn, self.nid)
        self.assertGreaterEqual(result["count"], 4)
        chars = novel_knowledge.get(self.conn, self.nid, category="character")
        su = next(c for c in chars if c["entity"] == "苏晚晴")
        self.assertEqual(su["content"], "筑基中期，痊愈")
        self.assertEqual(su["version"], 2)
        plots = novel_knowledge.get(self.conn, self.nid, category="plot")
        self.assertEqual(len(plots), 1)
        timeline = novel_knowledge.get(self.conn, self.nid, category="timeline")
        self.assertEqual(len(timeline), 2)

    def test_sync_latest_no_data(self):
        self.conn.execute("DELETE FROM chapter_summaries")
        self.conn.commit()
        result = novel_knowledge.sync_latest(self.conn)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["novel_id"])


if __name__ == "__main__":
    unittest.main()
