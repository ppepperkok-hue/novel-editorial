import unittest

from novel_pipeline import quality_gate


class QualityGateTests(unittest.TestCase):
    def test_count_chinese_chars(self):
        self.assertEqual(quality_gate.count_chinese_chars("你好，世界！abc"), 4)

    def test_punctuation_flags_halfwidth(self):
        issues = quality_gate.check_punctuation("他说,你好。")
        self.assertTrue(any("半角" in i for i in issues))

    def test_ai_flavor_density_detects_templates(self):
        density = quality_gate.ai_flavor_density("他突然冷笑一声，顿时沉默。")
        self.assertGreater(density, 0)

    def test_score_passes_clean_chapter(self):
        text = "重生之后的第一个清晨，林舟坐在高三教室里。" * 60
        report = quality_gate.score_chapter(
            text, ["重生", "林舟", "高三"], min_chars=800, max_chars=2000
        )
        self.assertTrue(report["passed"])

    def test_score_fails_short_chapter(self):
        report = quality_gate.score_chapter("太短", ["x"], min_chars=800, max_chars=1200)
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
