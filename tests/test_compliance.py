"""Compliance gate tests: built-in words, custom file merging, AI declaration."""

import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from novel_editorial import compliance


class ComplianceTests(unittest.TestCase):
    def _check_with_warnings(self, tmp_words_file, text):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with mock.patch.object(compliance, "WORDS_FILE", tmp_words_file):
                result = compliance.check(text)
        return result, caught

    def test_hits_builtin_word(self):
        result = compliance.check("本章出现冰毒交易描写")
        self.assertFalse(result["passed"])
        self.assertIn("冰毒", result["sensitive_hits"])

    def test_clean_text_passes(self):
        result = compliance.check("他推开门走进院子，风从巷口吹来。")
        self.assertTrue(result["passed"])
        self.assertEqual(result["sensitive_hits"], [])
        self.assertTrue(result["ai_declared"])

    def test_missing_words_file_warns(self):
        missing = Path(tempfile.mkdtemp()) / "missing_words.txt"
        result, caught = self._check_with_warnings(missing, "他推开门走进院子，风从巷口吹来。")
        self.assertIn(compliance.MISSING_WORDS_WARNING, result["warnings"])
        self.assertTrue(any(
            w.category is RuntimeWarning and str(w.message) == compliance.MISSING_WORDS_WARNING
            for w in caught
        ))

    def test_empty_words_file_warns(self):
        tmp = Path(tempfile.mkdtemp()) / "words.txt"
        tmp.write_text("", encoding="utf-8")
        result, caught = self._check_with_warnings(tmp, "他推开门走进院子，风从巷口吹来。")
        self.assertIn(compliance.EMPTY_WORDS_WARNING, result["warnings"])
        self.assertTrue(any(
            w.category is RuntimeWarning and str(w.message) == compliance.EMPTY_WORDS_WARNING
            for w in caught
        ))

    def test_all_comments_words_file_warns(self):
        tmp = Path(tempfile.mkdtemp()) / "words.txt"
        tmp.write_text("# 注释行一\n# 注释行二\n", encoding="utf-8")
        result, caught = self._check_with_warnings(tmp, "他推开门走进院子，风从巷口吹来。")
        self.assertIn(compliance.EMPTY_WORDS_WARNING, result["warnings"])
        self.assertTrue(any(
            w.category is RuntimeWarning and str(w.message) == compliance.EMPTY_WORDS_WARNING
            for w in caught
        ))

    def test_bad_encoding_words_file_warns_and_falls_back(self):
        tmp = Path(tempfile.mkdtemp()) / "words.txt"
        tmp.write_bytes(b"\xff\xfe\x00\xd6\xd0\xce\xc4")
        result, caught = self._check_with_warnings(tmp, "他推开门走进院子，风从巷口吹来。")
        self.assertIn(compliance.READ_WORDS_WARNING, result["warnings"])
        self.assertTrue(any(
            w.category is RuntimeWarning and str(w.message) == compliance.READ_WORDS_WARNING
            for w in caught
        ))
        self.assertTrue(result["passed"])

    def test_custom_words_file_is_merged(self):
        tmp = Path(tempfile.mkdtemp()) / "words.txt"
        tmp.write_text("# 注释\n自定义红线词\n", encoding="utf-8")
        result, caught = self._check_with_warnings(tmp, "正文包含自定义红线词")
        self.assertFalse(result["passed"])
        self.assertIn("自定义红线词", result["sensitive_hits"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(caught, [])

    def test_real_words_file_check_runs(self):
        self.assertTrue(compliance.WORDS_FILE.exists())
        custom_words = compliance._read_custom_words()
        self.assertIsInstance(custom_words, list)
        result = compliance.check("他推开门走进院子，风从巷口吹来。")
        self.assertTrue(result["passed"])
        self.assertIn("warnings", result)


if __name__ == "__main__":
    unittest.main()
