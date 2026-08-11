"""R4-1 tests: workday reminders."""

import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from novel_pipeline.services import reminders


class ReminderTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))
        self.conn.execute(
            "INSERT INTO novels(title,genre,premise,status) VALUES('书','都市','设定','publishing')"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _insert_workday(self, phase="awaiting_close", status="running"):
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,started_at,created_at) "
            "VALUES(?,?,?,?,?,?,'write',datetime('now','localtime'),datetime('now','localtime'))",
            ("wd-1", 1, "manual", "workday", status, phase),
        )
        self.conn.commit()

    def test_unopened_fires_once_per_day(self):
        with mock.patch.object(reminders, "_popup") as popup:
            r1 = reminders.check_and_notify(self.conn)
            r2 = reminders.check_and_notify(self.conn)
        self.assertEqual(r1["fired"], ["unopened"])
        self.assertEqual(r2["fired"], [])
        self.assertEqual(popup.call_count, 1)

    def test_opened_unpublished_fires(self):
        self._insert_workday(phase="producing", status="running")
        with mock.patch.object(reminders, "_popup") as popup:
            r = reminders.check_and_notify(self.conn)
        self.assertIn("unpublished", r["fired"])
        self.assertNotIn("unopened", r["fired"])
        self.assertEqual(popup.call_count, 1)

    def test_awaiting_close_fires_decision_reminder(self):
        self._insert_workday(phase="awaiting_close", status="running")
        with mock.patch.object(reminders, "_popup") as popup:
            r = reminders.check_and_notify(self.conn)
        self.assertIn("awaiting", r["fired"])
        self.assertEqual(popup.call_count, 1)

    def test_finished_workday_is_silent(self):
        self._insert_workday(phase="finished", status="completed")
        with mock.patch.object(reminders, "_popup") as popup:
            r = reminders.check_and_notify(self.conn)
        self.assertEqual(r["fired"], [])
        self.assertEqual(popup.call_count, 0)
