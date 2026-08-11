import json
import os
import tempfile
import unittest

from novel_editorial import db
from novel_editorial.llm_client import MockLLMClient
from novel_editorial.novel_flow import run_novel

PLAN = json.dumps({
    "title": "重启：从高三教室开始",
    "genre": "都市重生",
    "premise": "林舟重生回到高考前三个月。",
    "selling_point": "重生改写全家命运",
    "volume_goal": "高考前的三个月",
    "chapter_outlines": ["第1章 醒来", "第2章 第一步", "第3章 目标"],
    "keywords": ["林舟", "高三", "重生"],
}, ensure_ascii=False)

REVIEW = json.dumps({
    "scores": {"words": 10, "plot": 10, "style": 10,
               "punctuation": 10, "coherence": 10},
    "passed": True,
    "issues": [],
}, ensure_ascii=False)

MEMORY = json.dumps({
    "summary": "林舟在高三教室醒来，确认了重生的事实。",
    "character_states": {"林舟": {"goal": "改写命运", "emotion": "坚定"}},
    "world_events": [],
}, ensure_ascii=False)


class NovelFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "test.db"))
        self.client = MockLLMClient(responses={
            "planning": PLAN,
            "writing": "林舟坐在高三教室里，确认了重生的事实，他要改写命运。",
            "editing": "林舟坐在高三教室里，确认了重生的事实，他要改写命运。",
            "reviewing": REVIEW,
            "memory": MEMORY,
        })

    def test_run_novel_chains_three_chapters_with_memory(self):
        result = run_novel(self.conn, self.client, "林舟重生回到高考前三个月。",
                           chapters=3, min_chars=20, max_chars=60)
        self.assertTrue(result["all_passed"])
        self.assertEqual(len(result["chapters"]), 3)
        chapters = self.conn.execute("SELECT COUNT(*) c FROM chapters").fetchone()["c"]
        self.assertEqual(chapters, 3)
        summaries = self.conn.execute(
            "SELECT COUNT(*) c FROM chapter_summaries"
        ).fetchone()["c"]
        self.assertEqual(summaries, 3)
        self.assertEqual(self.client.calls[0]["tier"], "planning")


if __name__ == "__main__":
    unittest.main()
