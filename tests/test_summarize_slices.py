"""Tests for the slice review summarizer."""

import os
import tempfile
import unittest

from tools import summarize_slices


class SummarizeTests(unittest.TestCase):
    def test_summarize_merges_levels_and_totals(self):
        d = tempfile.mkdtemp()
        with open(
            os.path.join(d, "20260812-0100-slice-core.md"), "w", encoding="utf-8"
        ) as f:
            f.write(
                "# core\n"
                "- [P1] 假启动 — core.py:1\n"
                "- [P2] 静默失败 — core.py:2\n"
                "| 3 | P2 | 表格条目 | core.py:3 |\n"
            )
        with open(
            os.path.join(d, "20260812-0100-slice-tests.md"), "w", encoding="utf-8"
        ) as f:
            f.write("# tests\n- [P3] 测试缺口 — tests.py:1\n")

        result = summarize_slices.summarize(d, "20260812-0100")
        self.assertTrue(result["ok"])
        self.assertEqual(result["totals"], {0: 0, 1: 1, 2: 2, 3: 1})
        out = result["out"]
        text = open(out, encoding="utf-8").read()
        self.assertIn("## core", text)
        self.assertIn("假启动", text)
        self.assertIn("表格条目", text)
        self.assertIn("## tests", text)
        self.assertIn("| P1 | 1 |", text)

    def test_summarize_no_reports_returns_error(self):
        result = summarize_slices.summarize(tempfile.mkdtemp(), "nope-0000")
        self.assertFalse(result["ok"])
