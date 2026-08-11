import json
import os
import tempfile
import unittest

from novel_editorial import db
from tools import novel_knowledge


class NovelKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
        nid = db.add_novel(self.conn, "测试书", "都市", "简介")
        self.nid = nid
        vid = db.add_volume(self.conn, nid, 1, "第一卷")
        self.cid1 = db.add_chapter(self.conn, nid, vid, 1, "第一章")
        self.cid2 = db.add_chapter(self.conn, nid, vid, 2, "第二章")

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

    def test_upsert_same_content_is_idempotent(self):
        kid = novel_knowledge.upsert(
            self.conn, self.nid, "character", "苏晚晴",
            "筑基初期，重伤未愈", source_chapter=self.cid1,
        )
        kid2 = novel_knowledge.upsert(
            self.conn, self.nid, "character", "苏晚晴",
            "筑基初期，重伤未愈", source_chapter=self.cid2,
        )
        self.assertEqual(kid, kid2)
        items = novel_knowledge.get(self.conn, self.nid, category="character")
        self.assertEqual(items[0]["version"], 1, "same content must not bump version")
        hist = novel_knowledge.history(self.conn, kid)
        self.assertEqual(len(hist), 0, "same content must not write history")

    def test_normalize_entity(self):
        self.assertEqual(
            novel_knowledge.normalize_entity("world_rule", "阴阳守恒：殡仪馆是阴阳交界点"),
            "阴阳守恒",
        )
        self.assertEqual(
            novel_knowledge.normalize_entity("character", "沈老爷子（已故）"),
            "沈老爷子",
        )
        self.assertEqual(
            novel_knowledge.normalize_entity("item", "「破碗」"),
            "破碗",
        )
        long_name = "这是一个非常非常长的实体名称超过十六个字符"
        self.assertEqual(len(novel_knowledge.normalize_entity("plot", long_name)), 16)
        self.assertEqual(novel_knowledge.normalize_entity("character", "   "), "")

    def test_upsert_normalizes_entity(self):
        kid = novel_knowledge.upsert(
            self.conn, self.nid, "world_rule",
            "三香引魂：殡葬师以三炷香为号，一香问路",
            "三香引魂：殡葬师以三炷香为号，一香问路、二香开路、三香送魂。",
        )
        self.assertIsNotNone(kid)
        row = self.conn.execute(
            "SELECT entity FROM novel_knowledge WHERE id=?", (kid,)
        ).fetchone()
        self.assertEqual(row["entity"], "三香引魂")

    def test_upsert_ex_merges_similar_and_flags_conflict(self):
        base = novel_knowledge.upsert_ex(
            self.conn, self.nid, "world_rule", "阴阳守恒",
            "殡仪馆是阴阳交界点，活人误入阴路会折寿。",
        )
        self.assertTrue(base["id"])
        # A sentence-style entity normalizes to the exact same name, so it
        # version-updates the existing row instead of creating a duplicate.
        normalized = novel_knowledge.upsert_ex(
            self.conn, self.nid, "world_rule", "阴阳守恒：殡仪馆是阴阳交界点",
            "殡仪馆是阴阳交界点，活人误入阴路会折寿，死人闯入阳道会冲煞。",
            check_similar=True,
        )
        self.assertEqual(normalized["id"], base["id"])
        self.assertIsNone(normalized["merged_into"])
        rows = novel_knowledge.get(self.conn, self.nid, category="world_rule")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], 2)
        # A near-duplicate entity (different normalized name, similar content)
        # merges into the existing row and reports merged_into.
        merged = novel_knowledge.upsert_ex(
            self.conn, self.nid, "world_rule", "阴阳守恒律",
            "殡仪馆是阴阳交界点，活人误入阴路会折寿，死人闯入阳道会冲煞。",
            check_similar=True,
        )
        self.assertEqual(merged["id"], base["id"])
        self.assertEqual(merged["merged_into"], "阴阳守恒")
        rows = novel_knowledge.get(self.conn, self.nid, category="world_rule")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], 3)
        # Conflicting content for a similar-but-distinct entity queues a draft.
        conflicted = novel_knowledge.upsert_ex(
            self.conn, self.nid, "world_rule", "阴阳守恒之律",
            "与阴阳守恒完全冲突的另一套规则描述。",
            check_similar=True,
        )
        self.assertTrue(conflicted["id"])
        self.assertIsNone(conflicted["merged_into"])
        drafts = self.conn.execute(
            "SELECT COUNT(*) c FROM knowledge_drafts "
            "WHERE kind='knowledge' AND source='auto_conflict' AND status='draft'"
        ).fetchone()["c"]
        self.assertGreaterEqual(drafts, 1)

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

    def test_sync_from_chapters_updates_same_character_entity(self):
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
        self.assertNotIn("·状态", {c["entity"] for c in chars})
        plots = novel_knowledge.get(self.conn, self.nid, category="plot")
        self.assertEqual(len(plots), 1)
        self.assertEqual(plots[0]["entity"], "破碗认主")
        timeline = novel_knowledge.get(self.conn, self.nid, category="timeline")
        self.assertEqual(len(timeline), 2)

    def test_sync_latest_no_data(self):
        self.conn.execute("DELETE FROM chapter_summaries")
        self.conn.commit()
        result = novel_knowledge.sync_latest(self.conn)
        self.assertTrue(result["ok"])
        # No chapters yet: sync_latest still resolves the latest novel so the
        # story bible can initialize the knowledge store before chapter 1.
        self.assertEqual(result["novel_id"], self.nid)


if __name__ == "__main__":
    unittest.main()
