"""Compliance gate tests: built-in words, custom file merging, AI declaration."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_editorial import compliance


class ComplianceTests(unittest.TestCase):
    def test_hits_builtin_word(self):
        result = compliance.check("本章出现冰毒交易描写")
        self.assertFalse(result["passed"])
        self.assertIn("冰毒", result["sensitive_hits"])

    def test_clean_text_passes(self):
        result = compliance.check("他推开门走进院子，风从巷口吹来。")
        self.assertTrue(result["passed"])
        self.assertEqual(result["sensitive_hits"], [])
        self.assertTrue(result["ai_declared"])

    def test_custom_words_file_is_merged(self):
        tmp = Path(tempfile.mkdtemp()) / "words.txt"
        tmp.write_text("# 注释\n自定义红线词\n", encoding="utf-8")
        with mock.patch.object(compliance, "WORDS_FILE", tmp):
            result = compliance.check("正文包含自定义红线词")
            self.assertFalse(result["passed"])
            self.assertIn("自定义红线词", result["sensitive_hits"])


if __name__ == "__main__":
    unittest.main()
