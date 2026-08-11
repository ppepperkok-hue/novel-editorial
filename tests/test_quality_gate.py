import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from novel_editorial import quality_gate


class QualityGateTests(unittest.TestCase):
    def test_count_chinese_chars(self):
        self.assertEqual(quality_gate.count_chinese_chars("你好，世界！abc"), 4)

    def test_punctuation_flags_halfwidth(self):
        issues = quality_gate.check_punctuation("他说,你好。")
        self.assertTrue(any("半角" in i for i in issues))

    def test_ai_flavor_density_detects_templates(self):
        density = quality_gate.ai_flavor_density("他突然冷笑一声，顿时沉默。")
        self.assertGreater(density, 0)

    def test_ai_flavor_density_overlap_counts_once(self):
        with mock.patch.object(quality_gate, "AI_FLAVOR_WORDS", ["缓缓", "缓缓说道"]):
            density = quality_gate.ai_flavor_density("他缓缓说道。")
        self.assertEqual(
            density,
            1000 / quality_gate.count_chinese_chars("他缓缓说道。"),
        )

    def test_ai_flavor_density_empty_word_list_returns_zero(self):
        with mock.patch.object(quality_gate, "AI_FLAVOR_WORDS", []):
            density = quality_gate.ai_flavor_density("他突然冷笑一声，顿时沉默。")
        self.assertEqual(density, 0.0)

    def test_missing_ai_words_file_warns_and_falls_back(self):
        missing = Path(tempfile.mkdtemp()) / "missing_ai_words.json"
        with mock.patch.object(quality_gate, "_WORDS_FILE", missing):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                words = quality_gate._load_ai_flavor_words()
        self.assertEqual(words, quality_gate._DEFAULT_AI_FLAVOR_WORDS)
        self.assertTrue(any(w.category is RuntimeWarning for w in caught))

    def test_corrupt_ai_words_file_warns_and_falls_back(self):
        corrupt = Path(tempfile.mkdtemp()) / "corrupt_ai_words.json"
        corrupt.write_text("{ 不是合法 JSON", encoding="utf-8")
        with mock.patch.object(quality_gate, "_WORDS_FILE", corrupt):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                words = quality_gate._load_ai_flavor_words()
        self.assertEqual(words, quality_gate._DEFAULT_AI_FLAVOR_WORDS)
        self.assertTrue(any(w.category is RuntimeWarning for w in caught))

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
