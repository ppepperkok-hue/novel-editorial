import unittest

from novel_pipeline.economics import monthly_model


class EconomicsTests(unittest.TestCase):
    def test_attendance_active_scenario(self):
        m = monthly_model(cost_per_chapter=0.3, chapters_per_day=2, days=30,
                          full_attendance=600, listening_share=600)
        self.assertEqual(m["chapters"], 60)
        self.assertEqual(m["cost"], 18.0)
        self.assertTrue(m["attendance_active"])
        self.assertEqual(m["attendance_bonus"], 600.0)
        self.assertEqual(m["share_bonus"], 30.0)
        self.assertEqual(m["income"], 1230.0)
        self.assertEqual(m["profit"], 1212.0)

    def test_below_gate_disables_attendance(self):
        m = monthly_model(cost_per_chapter=0.3, chapters_per_day=2, days=30,
                          full_attendance=600, listening_share=200)
        self.assertFalse(m["attendance_active"])
        self.assertEqual(m["attendance_bonus"], 0.0)
        self.assertEqual(m["share_bonus"], 0.0)
        self.assertEqual(m["income"], 200.0)
        self.assertEqual(m["profit"], 182.0)

    def test_break_even_respects_gate(self):
        m = monthly_model(cost_per_chapter=0.3, chapters_per_day=2, days=30,
                          full_attendance=600, listening_share=600)
        self.assertEqual(m["break_even_listening_share"], 500.0)


if __name__ == "__main__":
    unittest.main()
