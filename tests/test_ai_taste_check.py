"""Tests for AI-taste detection rules."""

import unittest

from tools.ai_taste_check import EXCLAMATION_PATTERN, detect


class AiTasteTests(unittest.TestCase):
    def test_full_width_exclamation_patterns_detected(self):
        samples = [
            "？？", "！？", "？！", "？？？",
        ]
        for sample in samples:
            self.assertTrue(
                EXCLAMATION_PATTERN.search(sample),
                f"pattern must match {sample}",
            )

    def test_detect_reports_exclamations(self):
        result = detect("他愣住了？？怎么可能！？！？！？")
        self.assertTrue(
            any("连续感叹/问号" in n for n in result.get("notes", [])),
            result.get("notes"),
        )
