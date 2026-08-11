import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_pipeline import db
from novel_pipeline.services import knowledge


def make_tmp_knowledge():
    tmpdir = tempfile.mkdtemp()
    d = Path(tmpdir)
    (d / "opening.md").write_text(
        "---\ntitle: 开篇钩子\ntype: craft\n"
        "agents: [\"writer\", \"planner\"]\n"
        "keywords: [\"钩子\", \"开篇\"]\n"
        "source: test\nupdated_at: 2026-08-10\n---\n\n## 使用说明\n写章末钩子时对照。",
        encoding="utf-8",
    )
    (d / "market.md").write_text(
        "---\ntitle: 市场热点\ntype: market\n"
        "agents: [\"planner\"]\nkeywords: [\"市场\", \"题材\"]\n"
        "source: test\nupdated_at: 2026-08-10\n---\n\n## 使用说明\n选题时对照。",
        encoding="utf-8",
    )
    return d


class KnowledgeTests(unittest.TestCase):
    def test_list_and_read(self):
        with mock.patch.object(knowledge, "KNOWLEDGE_DIR", make_tmp_knowledge()):
            items = knowledge.list_knowledge()
            self.assertEqual(len(items), 2)
            opening = knowledge.read_knowledge("opening.md")
            self.assertEqual(opening["meta"]["type"], "craft")
            self.assertEqual(opening["meta"]["agents"], ["writer", "planner"])
            self.assertIn("使用说明", opening["body"])

    def test_write_roundtrip(self):
        d = make_tmp_knowledge()
        with mock.patch.object(knowledge, "KNOWLEDGE_DIR", d):
            knowledge.write_knowledge(
                "new.md",
                {"title": "新包", "type": "craft", "agents": ["all"]},
                "## 使用说明\n内容。",
            )
            item = knowledge.read_knowledge("new.md")
            self.assertEqual(item["meta"]["title"], "新包")
            self.assertEqual(item["meta"]["agents"], ["all"])
            self.assertIn("内容。", item["body"])

    def test_write_rejects_newline_in_frontmatter(self):
        d = make_tmp_knowledge()
        with mock.patch.object(knowledge, "KNOWLEDGE_DIR", d):
            with self.assertRaises(ValueError):
                knowledge.write_knowledge(
                    "bad.md",
                    {"title": "标题\n注入", "type": "craft"},
                    "内容",
                )

    def test_resolve_filters_by_agent_and_topic(self):
        with mock.patch.object(knowledge, "KNOWLEDGE_DIR", make_tmp_knowledge()):
            hits = knowledge.resolve_knowledge("writer", "钩子")
            self.assertEqual([h["file"] for h in hits], ["opening.md"])
            hits = knowledge.resolve_knowledge("reader", "钩子")
            self.assertEqual(hits, [])
            hits = knowledge.resolve_knowledge("planner", "")
            self.assertEqual(hits, [], "empty topic must not return every package")
            hits = knowledge.resolve_knowledge("planner", "钩子")
            self.assertEqual([h["file"] for h in hits], ["opening.md"])

    def test_index_only_applicable_packages(self):
        with mock.patch.object(knowledge, "KNOWLEDGE_DIR", make_tmp_knowledge()):
            idx = knowledge.build_knowledge_index("writer")
            self.assertIn("开篇钩子", idx)
            self.assertNotIn("市场热点", idx)

    def test_clean_title_strips_font_glyphs(self):
        dirty = "笨蛋\ue001\ue002替嫁\ue003疯批王爷宠\ue004"
        cleaned = knowledge.clean_title(dirty)
        self.assertEqual(cleaned, "笨蛋替嫁疯批王爷宠")

    def test_drafts_crud(self):
        conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
        try:
            did = knowledge.add_draft(
                conn, "lesson", "经验", "内容", agent="writer",
                source="meeting:1", agents=["writer", "planner"],
            )
            drafts = knowledge.list_drafts(conn)
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]["agents"], ["writer", "planner"])
            self.assertTrue(knowledge.update_draft_status(conn, did, "accepted"))
            self.assertFalse(knowledge.update_draft_status(conn, did, "rejected"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
