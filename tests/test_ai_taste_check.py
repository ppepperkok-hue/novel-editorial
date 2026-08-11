"""Tests for AI-taste detection rules."""

import unittest

from tools.ai_taste_check import (
    EXCLAMATION_PATTERN,
    count_non_overlap,
    count_occurrences,
    density_per_window,
    detect,
)


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

    def test_exclamation_pattern_ignores_single_marks(self):
        self.assertIsNone(EXCLAMATION_PATTERN.search("他说了一句！然后问？"))

    def test_detect_empty_and_falsy_inputs(self):
        empty_report = {
            "score": 0,
            "flowery": {},
            "filler": {},
            "density": 0,
            "notes": [],
            "chars": 0,
        }
        for value in ("", None, 0):
            self.assertEqual(detect(value), empty_report)

    def test_detect_plain_text_has_no_notes(self):
        text = "他推门走进教室，把书包放在桌上。"
        result = detect(text)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["flowery"], {})
        self.assertEqual(result["filler"], {})
        self.assertEqual(result["density"], 0)
        self.assertEqual(result["notes"], [])
        self.assertEqual(result["chars"], len(text))

    def test_non_overlap_counting_shared_words(self):
        words = ["微微一", "微微一愣"]
        self.assertEqual(count_non_overlap("微微一怔", words), 1)
        self.assertEqual(count_occurrences("微微一怔", words), {"微微一": 1})
        self.assertEqual(count_non_overlap("微微一怔，微微一怔", words), 2)

    def test_density_per_window_basis(self):
        self.assertEqual(density_per_window(2, 500), 2.0)
        self.assertEqual(density_per_window(2, 1000), 1.0)
        self.assertEqual(density_per_window(1, 1500), 0.33)

    def test_detect_flowery_density_notes_and_details(self):
        text = "璀璨耀眼磅礴深邃浩瀚凛冽"
        result = detect(text)
        self.assertEqual(
            result["flowery"],
            {
                "璀璨": 1,
                "耀眼": 1,
                "磅礴": 1,
                "深邃": 1,
                "浩瀚": 1,
                "凛冽": 1,
            },
        )
        self.assertGreater(result["density"], 2)
        self.assertTrue(
            any("华丽辞藻密度" in n and "超过阈值" in n for n in result["notes"])
        )
        self.assertGreaterEqual(result["score"], 48)
        self.assertEqual(result["chars"], len(text))

    def test_detect_low_flowery_density_still_notes(self):
        result = detect("璀璨" + "好" * 1000)
        self.assertEqual(result["flowery"], {"璀璨": 1})
        self.assertGreater(result["density"], 0)
        self.assertLessEqual(result["density"], 2)
        self.assertTrue(
            any("华丽辞藻密度" in n and "可接受但留意" in n for n in result["notes"])
        )

    def test_detect_filler_overflow_note(self):
        text = "突然，他不由自主地停下了；与此同时，仿佛隐约听见什么，微微一愣，缓缓说道：“走吧。”"
        result = detect(text)
        self.assertEqual(result["filler"]["突然"], 1)
        self.assertEqual(result["filler"]["微微一愣"], 1)
        self.assertTrue(
            any("AI 味短语命中 7 次" in n for n in result["notes"]),
            result.get("notes"),
        )

    def test_detect_exclamation_threshold_note(self):
        result = detect("？！？！？！？！")
        self.assertTrue(
            any("连续感叹/问号 4 处" in n for n in result["notes"]),
            result.get("notes"),
        )

    def test_detect_four_char_stacking_note(self):
        text = "璀璨耀眼磅礴深邃，璀璨耀眼磅礴深邃"
        result = detect(text)
        self.assertTrue(
            any("疑似四字排比堆砌 2 处" in n for n in result["notes"]),
            result.get("notes"),
        )
