"""Regression tests for service-layer gaps found in the strict review."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402


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
    def test_outputs_settings_plus_db_arg(self):
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
        self.assertEqual(payload["novel_premise"], "测试设定")


class ControlTests(unittest.TestCase):
    def test_save_settings_whitelist_and_run_now(self):
        path = make_db()
        from novel_pipeline.services import control

        conn = db.connect(path)
        try:
            result = control.handle_control(
                conn,
                {"action": "save_settings", "settings": {"monthly_budget": "88", "evil": "x"}},
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["saved"], {"monthly_budget": "88"})
            with mock.patch("novel_pipeline.services.control.run_workflow_now") as run:
                run.return_value = {"ok": True, "response": "{}", "workflow": "daily"}
                result = control.handle_control(conn, {"action": "run_now", "workflow": "daily"})
            self.assertTrue(result["ok"])
            run.assert_called_once_with("daily")
        finally:
            conn.close()


class MiscTests(unittest.TestCase):
    def test_diary_list_and_update(self):
        path = make_db()
        from novel_pipeline.services import misc

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


class N8nServiceTests(unittest.TestCase):
    def test_api_key_empty_not_cached(self):
        from novel_pipeline.services import n8n as n8n_service

        n8n_service._N8N_KEY = None
        with mock.patch(
            "novel_pipeline.services.n8n.config.env_value", return_value=""
        ) as env:
            with mock.patch.dict(os.environ, {}, clear=False):
                self.assertEqual(n8n_service._load_n8n_env(), "")
            self.assertIsNone(n8n_service._N8N_KEY, "empty key must not be cached")
            env.return_value = "key123"
            self.assertEqual(n8n_service._load_n8n_env(), "key123")
            self.assertEqual(n8n_service._N8N_KEY, "key123")
        n8n_service._N8N_KEY = None


if __name__ == "__main__":
    unittest.main()
