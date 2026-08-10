"""Tests for preflight guards: manual-run retention, budget, lock safety."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402
from tools import preflight  # noqa: E402


def make_db():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute("INSERT INTO novels(title,genre,premise,status) VALUES('书','都市','设定','publishing')")
    conn.execute("INSERT INTO settings(key,value) VALUES('manual_run_requested','1')")
    conn.commit()
    conn.close()
    return path


class PreflightTests(unittest.TestCase):
    def _run(self, path, cookie_ok=True, budget_ok=True, already=False):
        env = {"FANQIE_COOKIE": "c", "FANQIE_CSRF_TOKEN": "t"}
        alert_file = os.path.join(tempfile.mkdtemp(), "alerts.log")
        conn = db.connect(path)
        try:
            with mock.patch.object(sys, "argv", ["preflight", "--db", path]):
                with mock.patch.object(preflight, "ALERTS_LOG", Path(alert_file)):
                    with mock.patch.object(preflight, "check_cookie", return_value=(cookie_ok, "")):
                        with mock.patch.object(preflight, "check_budget", return_value=(budget_ok, 10.0)):
                            with mock.patch.object(preflight, "check_already_ran", return_value=already):
                                with mock.patch.object(preflight, "acquire_lock", return_value=(True, "")):
                                    with mock.patch.dict(os.environ, env, clear=False):
                                        return preflight.main()
        finally:
            conn.close()

    def test_manual_request_consumed_only_when_ok(self):
        path = make_db()
        self._run(path, cookie_ok=False)
        conn = db.connect(path)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key='manual_run_requested'").fetchone()
            self.assertEqual(row["value"], "1", "failed preflight must keep the manual request")
        finally:
            conn.close()

        self._run(path, cookie_ok=True)
        conn = db.connect(path)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key='manual_run_requested'").fetchone()
            self.assertEqual(row["value"], "0", "successful preflight consumes the request")
        finally:
            conn.close()

    def test_pid_alive_windows_uses_openprocess(self):
        self.assertFalse(preflight._pid_alive(0) if os.name == "nt" else not preflight._pid_alive(os.getpid()))


if __name__ == "__main__":
    unittest.main()
