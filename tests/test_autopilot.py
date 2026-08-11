import json
import os
import tempfile
import unittest

from novel_pipeline import db
from novel_pipeline.autopilot import daily_run
from novel_pipeline.llm_client import MockLLMClient
from novel_pipeline.publisher import ManualAdapter

PLAN = json.dumps({
    "title": "重启：从高三教室开始",
    "genre": "都市重生",
    "premise": "林舟重生回到高考前三个月。",
    "selling_point": "重生改写全家命运",
    "volume_goal": "高考前的三个月",
    "chapter_outlines": ["第1章 醒来", "第2章 第一步", "第3章 目标",
                         "第4章 计划", "第5章 行动"],
    "keywords": ["林舟", "高三", "重生"],
}, ensure_ascii=False)

PLAN_3 = json.dumps({
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


class AutopilotTests(unittest.TestCase):
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
        self.env = {"TOMATO_COOKIE": "c", "TOMATO_CSRF_TOKEN": "t"}
        self.queue_file = os.path.join(self.tmpdir, "publish_queue.jsonl")

    def test_daily_run_generates_publishes_and_passes_health_check(self):
        result = daily_run(
            self.conn, self.client, "林舟重生回到高考前三个月。",
            chapters=5, chapters_per_day=2, min_chars=20, max_chars=60,
            env=self.env, adapter=ManualAdapter(queue_path=self.queue_file),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["publish"]["published"]), 2)
        self.assertEqual(result["health_issues"], [])
        statuses = [r["status"] for r in
                    self.conn.execute("SELECT status FROM chapters ORDER BY seq")]
        self.assertEqual(statuses, ["published", "published",
                                    "reviewed", "reviewed", "reviewed"])

    def test_daily_run_warns_when_backlog_below_safe_line(self):
        # Only publishing/finishing books produce stock warnings now; the
        # auto-generated book stays planning, so seed a real serialized book.
        nid = db.add_novel(self.conn, "连载书", "都市", "设定")
        self.conn.execute("UPDATE novels SET status='publishing' WHERE id=?", (nid,))
        self.conn.commit()
        self.client.responses["planning"] = PLAN_3
        result = daily_run(
            self.conn, self.client, "林舟重生回到高考前三个月。",
            chapters=3, chapters_per_day=2, min_chars=20, max_chars=60,
            env=self.env, adapter=ManualAdapter(queue_path=self.queue_file),
        )
        self.assertFalse(result["ok"])
        self.assertTrue(any("存稿池" in i for i in result["health_issues"]))


if __name__ == "__main__":
    unittest.main()
