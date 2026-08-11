import json
import os
import tempfile
import unittest

from novel_editorial import db
from novel_editorial.llm_client import MockLLMClient
from novel_editorial.pipeline import run_generation

OUTLINE = {
    "title": "重启：从高三教室开始",
    "genre": "都市重生",
    "premise": "林舟重生回到高考前三个月。",
    "volume_goal": "第一卷",
    "chapter_outline": "第1章：林舟确认重生，定下目标。",
    "platform": "fanqie",
    "keywords": ["林舟", "高三", "重生"],
}

REVIEW = json.dumps(
    {
        "scores": {"words": 10, "plot": 10, "style": 10,
                   "punctuation": 10, "coherence": 10},
        "passed": True,
        "issues": [],
    },
    ensure_ascii=False,
)

MEMORY = json.dumps(
    {
        "summary": "林舟在高三教室醒来并确认重生。",
        "character_states": {"林舟": {"goal": "改写命运", "emotion": "坚定"}},
        "world_events": [],
    },
    ensure_ascii=False,
)


class RunGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "test.db"))
        self.client = MockLLMClient(responses={
            "writing": "林舟坐在高三教室里，确认了重生的事实，他要改写命运。",
            "editing": "林舟坐在高三教室里，确认了重生的事实，他要改写命运。",
            "reviewing": REVIEW,
            "memory": MEMORY,
        })

    def test_generation_persists_reviewed_chapter_and_summary(self):
        result = run_generation(self.conn, self.client, OUTLINE, min_chars=20, max_chars=60)
        self.assertTrue(result["passed"])
        chapter = self.conn.execute(
            "SELECT * FROM chapters WHERE id=?", (result["chapter_id"],)
        ).fetchone()
        self.assertEqual(chapter["status"], "reviewed")
        summary_count = self.conn.execute(
            "SELECT COUNT(*) c FROM chapter_summaries"
        ).fetchone()["c"]
        self.assertEqual(summary_count, 1)

    def test_generation_retries_until_review_passes(self):
        fail_review = json.dumps({
            "scores": {"words": 5, "plot": 5, "style": 5,
                       "punctuation": 5, "coherence": 5},
            "passed": False,
            "issues": ["节奏拖沓"],
            "suggestions": ["加快节奏，删减冗余描写"],
        }, ensure_ascii=False)
        client = MockLLMClient(responses={
            "writing": "林舟坐在高三教室里，确认了重生的事实，他要改写命运。",
            "editing": "林舟坐在高三教室里，确认了重生的事实，他要改写命运。",
            "reviewing": [fail_review, REVIEW],
            "memory": MEMORY,
        })
        result = run_generation(self.conn, client, OUTLINE, min_chars=20, max_chars=60)
        self.assertTrue(result["passed"])
        self.assertEqual(result["revisions"], 1)
        report = self.conn.execute(
            "SELECT revision_count FROM quality_reports WHERE chapter_id=?",
            (result["chapter_id"],),
        ).fetchone()
        self.assertEqual(report["revision_count"], 1)


if __name__ == "__main__":
    unittest.main()
