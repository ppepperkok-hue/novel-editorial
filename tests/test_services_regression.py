"""Regression tests for service-layer gaps found in the strict review."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_editorial import db  # noqa: E402


def make_db():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute("INSERT INTO novels(title,genre,premise,status) VALUES('书','都市','设定','publishing')")
    conn.execute("INSERT INTO chapters(novel_id,seq,outline,status,title) VALUES(1,1,'章纲','reviewed','第 1 章')")
    conn.commit()
    conn.close()
    return path


class CheckStockTests(unittest.TestCase):
    def test_outputs_active_novel_metadata(self):
        path = make_db()
        from tools import check_stock

        conn = db.connect(path)
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('novel_premise','测试设定') "
            "ON CONFLICT(key) DO UPDATE SET value='测试设定'"
        )
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('daily_chapters','2') "
            "ON CONFLICT(key) DO UPDATE SET value='2'"
        )
        conn.commit()
        conn.close()
        with mock.patch.object(sys, "argv", ["check_stock", "--db", path]):
            with mock.patch("builtins.print") as print_mock:
                check_stock.main()
        payload = json.loads(print_mock.call_args[0][0])
        self.assertEqual(payload["stock"], 1)
        self.assertEqual(payload["need"], 1)
        # book isolation: the active publishing novel wins over settings
        self.assertEqual(payload["novel_premise"], "设定")
        self.assertEqual(payload["book_name"], "书")
        self.assertEqual(payload["novel_id"], 1)

    def test_falls_back_to_settings_when_no_book(self):
        path = make_db()
        from tools import check_stock

        conn = db.connect(path)
        conn.execute("DELETE FROM chapters")
        conn.execute("DELETE FROM novels")
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('novel_premise','测试设定') "
            "ON CONFLICT(key) DO UPDATE SET value='测试设定'"
        )
        conn.commit()
        conn.close()
        with mock.patch.object(sys, "argv", ["check_stock", "--db", path]):
            with mock.patch("builtins.print") as print_mock:
                check_stock.main()
        payload = json.loads(print_mock.call_args[0][0])
        self.assertEqual(payload["novel_premise"], "测试设定")
        self.assertEqual(payload["book_id"], "")


class ControlTests(unittest.TestCase):
    def test_load_control_returns_scheduler_state_without_n8n(self):
        path = make_db()
        from novel_editorial.services import control

        conn = db.connect(path)
        try:
            payload = control.load_control(conn)
            self.assertIn("scheduler", payload)
            self.assertNotIn("workflows", payload)
            self.assertIn("enabled", payload["scheduler"])
            self.assertIn("last_run", payload["scheduler"])
        finally:
            conn.close()

    def test_save_settings_whitelist_and_run_now(self):
        path = make_db()
        from novel_editorial.services import control

        conn = db.connect(path)
        try:
            result = control.handle_control(
                conn,
                {"action": "save_settings", "settings": {"monthly_budget": "88", "evil": "x"}},
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["saved"], {"monthly_budget": "88"})
            with mock.patch("novel_editorial.services.control.run_workflow_now") as run:
                run.return_value = {"ok": True, "started": True, "workflow": "daily"}
                result = control.handle_control(conn, {"action": "run_now", "workflow": "daily"})
            self.assertTrue(result["ok"])
            run.assert_called_once_with("daily")
        finally:
            conn.close()

    def test_collect_reader_stats_cli_env_file_defined(self):
        import io  # noqa: PLC0415
        from contextlib import redirect_stdout  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415

        import tools.collect_reader_stats as collector

        with mock.patch("sys.argv", ["collect_reader_stats.py", "--help"]):
            with redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    collector.main()
        self.assertIn(ctx.exception.code, (0, None))

    def test_run_workflow_daily_actually_starts(self):
        from novel_editorial.services import control

        with mock.patch(
            "novel_editorial.services.control._background_daily"
        ) as bg:
            result = control.run_workflow_now("daily")
        self.assertTrue(result["ok"])
        bg.assert_called_once()

    def test_run_cli_reports_nonzero_exit(self):
        from novel_editorial.services import control

        with mock.patch("novel_editorial.services.control.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stderr = "boom"
            with mock.patch("novel_editorial.services.control._alert") as alert:
                ok = control._run_cli("tools/x.py", [])
        self.assertFalse(ok)
        alert.assert_called_once()
        self.assertIn("boom", alert.call_args.args[0])

    def test_run_now_chapters_capped_at_five(self):
        path = make_db()
        from novel_editorial.services import control

        conn = db.connect(path)
        try:
            with mock.patch("novel_editorial.services.control.run_workflow_now") as run:
                run.return_value = {"ok": True, "workflow": "daily"}
                result = control.handle_control(
                    conn, {"action": "run_now", "workflow": "daily", "chapters": 9}
                )
            self.assertTrue(result["ok"])
            row = conn.execute(
                "SELECT value FROM settings WHERE key='pending_publish'"
            ).fetchone()
            self.assertEqual(row["value"], "5")
        finally:
            conn.close()

    def test_pause_resume_keeper_workflow(self):
        path = make_db()
        from novel_editorial.services import control

        conn = db.connect(path)
        try:
            result = control.handle_control(conn, {"action": "pause", "workflow": "keeper"})
            self.assertTrue(result["ok"])
            self.assertIn("无独立开关", result["note"])
            result = control.handle_control(conn, {"action": "pause", "workflow": "daily"})
            self.assertTrue(result["ok"])
            row = conn.execute(
                "SELECT value FROM settings WHERE key='daily_enabled'"
            ).fetchone()
            self.assertEqual(row["value"], "false")
            result = control.handle_control(conn, {"action": "resume", "workflow": "daily"})
            self.assertTrue(result["ok"])
            row = conn.execute(
                "SELECT value FROM settings WHERE key='daily_enabled'"
            ).fetchone()
            self.assertEqual(row["value"], "true")
        finally:
            conn.close()

    def test_weekly_worker_skips_when_lock_held(self):
        from novel_editorial.services import control

        with mock.patch(
            "tools.preflight.acquire_lock",
            return_value=(False, "已有周会在途"),
        ) as acq:
            with mock.patch("novel_editorial.services.control._run_cli") as cli:
                with mock.patch("novel_editorial.services.control._alert") as alert:
                    control._weekly_worker()
        acq.assert_called_once()
        cli.assert_not_called()
        alert.assert_called_once()
        self.assertIn("已有周会在途", alert.call_args[0][0])

    def test_weekly_worker_releases_lock(self):
        from novel_editorial.services import control

        lock_path = control.ROOT / "n8n_tmp" / "weekly.lock"
        if lock_path.exists():
            lock_path.unlink()
        with mock.patch(
            "tools.preflight.acquire_lock",
            return_value=(True, ""),
        ):
            with mock.patch("novel_editorial.services.control._run_cli"):
                with mock.patch(
                    "tools.preflight.release_lock"
                ) as release:
                    control._weekly_worker()
        release.assert_called_once_with(lock_path)
        if lock_path.exists():
            lock_path.unlink()

    def test_process_messages_returns_unread_summary(self):
        path = make_db()
        from novel_editorial.services import control
        from tools import mailroom

        conn = db.connect(path)
        try:
            mailroom.send(conn, "reviewer", "writer", "打回", novel_id=1)
            result = control.handle_control(conn, {"action": "process_messages"})
            self.assertTrue(result["ok"])
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["agents"]["writer"], 1)
        finally:
            conn.close()


class MiscTests(unittest.TestCase):
    def test_diary_list_and_update(self):
        path = make_db()
        from novel_editorial.services import misc

        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO agent_diaries(agent,novel_id,diary_type,content,created_at) "
                "VALUES('planner',1,'daily','{}',datetime('now','localtime'))"
            )
            conn.commit()
            rows = misc.list_diaries(conn, agent="planner")
            self.assertEqual(len(rows), 1)
            result = misc.update_diary(conn, rows[0]["id"], {"what_done": "x"})
            self.assertTrue(result["ok"])
            rows = misc.list_diaries(conn, agent="planner")
            self.assertEqual(rows[0]["content"]["what_done"], "x")
        finally:
            conn.close()

    def test_audit_list_logs_filters_by_date_range(self):
        path = make_db()
        from novel_editorial.services import audit

        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO audit_logs(created_at,category,action,target_type,target_id,detail,source) "
                "VALUES('2026-08-01 10:00:00','operation','old','novel',1,'{}','test')"
            )
            conn.execute(
                "INSERT INTO audit_logs(created_at,category,action,target_type,target_id,detail,source) "
                "VALUES('2026-08-10 10:00:00','operation','new','novel',1,'{}','test')"
            )
            conn.commit()
            rows = audit.list_logs(conn, date_from="2026-08-09", date_to="2026-08-11")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["action"], "new")
            rows2 = audit.list_logs(conn, date_from="2026-08-02")
            self.assertEqual(len(rows2), 1)
            self.assertEqual(rows2[0]["action"], "new")
            rows3 = audit.list_logs(conn, date_to="2026-08-02")
            self.assertEqual(len(rows3), 1)
            self.assertEqual(rows3[0]["action"], "old")
        finally:
            conn.close()


class N8nServiceTests(unittest.TestCase):
    def test_api_key_empty_not_cached(self):
        from novel_editorial.services import n8n as n8n_service

        n8n_service._N8N_KEY = None
        with mock.patch(
            "novel_editorial.services.n8n.config.env_value", return_value=""
        ) as env:
            with mock.patch.dict(os.environ, {"N8N_API_KEY": ""}, clear=False):
                self.assertEqual(n8n_service._load_n8n_env(), "")
            self.assertIsNone(n8n_service._N8N_KEY, "empty key must not be cached")
            env.return_value = "key123"
            self.assertEqual(n8n_service._load_n8n_env(), "key123")
            self.assertEqual(n8n_service._N8N_KEY, "key123")
        n8n_service._N8N_KEY = None

    def test_workflow_status_includes_node_count(self):
        from novel_editorial.services import n8n as n8n_service

        with mock.patch(
            "novel_editorial.services.n8n.n8n_api",
            return_value={
                "active": True,
                "nodes": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            },
        ):
            info = n8n_service.workflow_status("wf-1")
        self.assertEqual(info["nodes"], 3)
        self.assertTrue(info["online"])


if __name__ == "__main__":
    unittest.main()
