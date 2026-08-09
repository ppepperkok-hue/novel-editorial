import unittest

from novel_pipeline.llm_client import MockLLMClient
from novel_pipeline.planner import build_outline

VALID_PLAN = """```json
{
  "title": "重启：从高三教室开始",
  "genre": "都市重生",
  "premise": "林舟重生回到高考前三个月。",
  "selling_point": "重生改写全家命运",
  "volume_goal": "高考前的三个月",
  "chapter_outlines": ["第1章 醒来", "第2章 第一步"],
  "keywords": ["林舟", "高三", "重生"]
}
```"""


class PlannerTests(unittest.TestCase):
    def test_build_outline_validates_and_returns(self):
        client = MockLLMClient(responses={"planning": VALID_PLAN})
        outline = build_outline(client, "林舟重生回到高考前三个月。", chapters=2)
        self.assertEqual(outline["title"], "重启：从高三教室开始")
        self.assertEqual(len(outline["chapter_outlines"]), 2)
        self.assertEqual(outline["platform"], "fanqie")

    def test_missing_field_raises(self):
        client = MockLLMClient(responses={"planning": '{"title": "只有书名"}'})
        with self.assertRaises(ValueError):
            build_outline(client, "设定", chapters=2)

    def test_chapter_count_mismatch_raises(self):
        client = MockLLMClient(responses={"planning": VALID_PLAN})
        with self.assertRaises(ValueError):
            build_outline(client, "设定", chapters=3)


if __name__ == "__main__":
    unittest.main()
