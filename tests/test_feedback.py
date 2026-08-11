import os
import tempfile
import unittest

from novel_editorial import data_feedback


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write("chapter,finish_rate,follow_rate\n1,0.28,0.41\n2,0.15,0.22\n")

    def test_report_marks_low_performers(self):
        rows = data_feedback.load_reader_stats(self.path)
        report = data_feedback.feedback_report(rows)
        self.assertEqual(report["chapters"], 2)
        self.assertIn(2, report["low_chapters"])

    def test_low_performers_empty_when_all_above_threshold(self):
        rows = [{"chapter": 1, "finish_rate": 0.3, "follow_rate": 0.4}]
        self.assertEqual(data_feedback.low_performers(rows), [])


if __name__ == "__main__":
    unittest.main()
