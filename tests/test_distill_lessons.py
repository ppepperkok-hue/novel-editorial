import json
import os
import tempfile
import unittest
from unittest import mock

from novel_editorial import db
from novel_editorial.services import knowledge
from tools import distill_lessons


class DistillLessonsTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
        self.conn.execute(
            "INSERT INTO weekly_meetings(held_at,novel_id,attendees,topics,report,status,kind) "
            "VALUES('2026-08-10 10:00:00',0,'[\"planner\"]','[\"选题\"]',?, 'completed','topic')",
            (
                json.dumps(
                    {
                        "discussion_summary": "讨论第一本书写什么",
                        "decisions": {"next_book": {"book_name": "测试书"}},
                        "action_items": [],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_distill_writes_drafts(self):
        output = {
            "lessons": [
                {
                    "agent": "planner",
                    "title": "选题要看热点",
                    "content": "下次选题先对照市场知识包，避免闭门造车。",
                    "agents": ["planner", "reader"],
                    "reason": "会议讨论显示热点数据未被使用",
                }
            ]
        }
        with mock.patch(
            "tools.distill_lessons.chat_deepseek",
            return_value={
                "text": json.dumps(output, ensure_ascii=False),
                "usage": {},
                "model": "deepseek-v4-flash",
            },
        ):
            result = distill_lessons.distill(self.conn)
        self.assertTrue(result["ok"])
        self.assertEqual(result["drafted"], 1)
        drafts = knowledge.list_drafts(self.conn)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["kind"], "lesson")
        self.assertEqual(drafts[0]["source"], "meeting:1")
        self.assertEqual(drafts[0]["agents"], ["planner", "reader"])

    def test_distill_without_meeting_returns_error(self):
        self.conn.execute("DELETE FROM weekly_meetings")
        self.conn.commit()
        result = distill_lessons.distill(self.conn)
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
