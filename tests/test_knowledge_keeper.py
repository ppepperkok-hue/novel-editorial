import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_pipeline import db
from novel_pipeline.services import knowledge
from tools import knowledge_keeper


def make_knowledge_dir():
    d = Path(tempfile.mkdtemp())
    (d / "market.md").write_text(
        "---\ntitle: 市场热点\ntype: market\nagents: [\"planner\"]\n"
        "keywords: [\"市场\"]\nsource: test\nupdated_at: 2026-08-10\n---\n\n旧市场内容",
        encoding="utf-8",
    )
    (d / "craft.md").write_text(
        "---\ntitle: 技巧包\ntype: craft\nagents: [\"writer\"]\n"
        "keywords: [\"技巧\"]\nsource: test\nupdated_at: 2026-08-10\n---\n\n旧技巧内容",
        encoding="utf-8",
    )
    return d


class KnowledgeKeeperTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))

    def tearDown(self):
        self.conn.close()

    def test_run_updates_market_only_and_drafts_rest(self):
        kdir = make_knowledge_dir()
        keeper_output = {
            "auto_updates": [
                {"file": "market.md", "body": "## 使用说明\n最新市场数据"},
                {"file": "craft.md", "body": "不应该被直接改"},
            ],
            "draft_suggestions": [
                {
                    "title": "伏笔回收要提前规划",
                    "content": "本周三次伏笔拖期，下次在细纲里标注回收窗口。",
                    "agents": ["planner", "guard"],
                }
            ],
            "deprecations": [
                {"file": "old-rule.md", "reason": "与最新读者数据矛盾"}
            ],
        }
        with (
            mock.patch.object(knowledge, "KNOWLEDGE_DIR", kdir),
            mock.patch(
                "tools.knowledge_keeper.chat_deepseek",
                return_value={
                    "text": json.dumps(keeper_output, ensure_ascii=False),
                    "usage": {},
                    "model": "deepseek-v4-flash",
                },
            ),
        ):
            result = knowledge_keeper.run(self.conn)

        self.assertEqual(result["auto_updates"], ["market.md"])
        market = (kdir / "market.md").read_text(encoding="utf-8")
        self.assertIn("最新市场数据", market)
        craft = (kdir / "craft.md").read_text(encoding="utf-8")
        self.assertIn("旧技巧内容", craft)
        drafts = knowledge.list_drafts(self.conn)
        kinds = [d["kind"] for d in drafts]
        self.assertIn("knowledge", kinds)
        self.assertIn("deprecation", kinds)
        lesson = next(d for d in drafts if d["kind"] == "knowledge")
        self.assertEqual(lesson["agents"], ["planner", "guard"])
        audit = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE action='keeper_run'"
        ).fetchone()["c"]
        self.assertEqual(audit, 1)


if __name__ == "__main__":
    unittest.main()
