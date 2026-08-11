"""Tests for the daily-run trace persistence (tools/daily_runs.py)."""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from novel_pipeline import db
from tools import daily_runs


def make_env():
    path = os.path.join(tempfile.mkdtemp(), f"t-{os.urandom(4).hex()}.db")
    conn = db.connect(path)
    nid = db.add_novel(conn, "测试书", "都市", "简介")
    conn.execute(
        "UPDATE novels SET status='publishing', book_id='1' WHERE id=?", (nid,)
    )
    conn.commit()
    conn.close()
    return path, nid


def _now_local():
    return (datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")


class DailyRunsTests(unittest.TestCase):
    def test_sync_persists_and_is_idempotent(self):
        path, nid = make_env()
        conn = db.connect(path)
        fake_n8n_db = os.path.join(tempfile.mkdtemp(), "n8n.sqlite")
        n = sqlite3.connect(fake_n8n_db)
        n.execute(
            "CREATE TABLE execution_entity (id INTEGER, workflowId TEXT, mode TEXT, "
            "status TEXT, startedAt TEXT, stoppedAt TEXT, deletedAt TEXT)"
        )
        n.execute(
            "INSERT INTO execution_entity VALUES "
            "(1001,'SkLUnm3uRyBSY84F','manual','success',"
            "'2026-08-11 04:31:19.793','2026-08-11 05:32:12.837',NULL),"
            "(1000,'SkLUnm3uRyBSY84F','scheduled','crashed',"
            "'2026-08-10 18:06:23.107','2026-08-10 18:06:23.112',NULL)"
        )
        n.commit()
        n.close()
        try:
            with mock.patch.object(daily_runs, "N8N_DB", Path(fake_n8n_db)):
                with mock.patch.object(
                    daily_runs, "_execution_failure",
                    return_value=(["预检"], "预检失败"),
                ):
                    first = daily_runs.sync_from_n8n(conn, limit=10)
                    second = daily_runs.sync_from_n8n(conn, limit=10)
            self.assertEqual(first["written"], 2)
            self.assertEqual(second["written"], 0)
            rows = conn.execute("SELECT run_id FROM daily_runs").fetchall()
            self.assertEqual(len(rows), 2)
            crashed = conn.execute(
                "SELECT status, failed_nodes, error FROM daily_runs WHERE run_id='1000'"
            ).fetchone()
            self.assertEqual(crashed["status"], "crashed")
            self.assertEqual(json.loads(crashed["failed_nodes"]), ["预检"])
            self.assertEqual(crashed["error"], "预检失败")
            source = conn.execute(
                "SELECT source FROM daily_runs WHERE run_id='1001'"
            ).fetchone()
            self.assertEqual(source["source"], "n8n-legacy")
            # UTC timestamps are shifted to local (+8)
            ok = conn.execute(
                "SELECT started_at, finished_at FROM daily_runs WHERE run_id='1001'"
            ).fetchone()
            self.assertEqual(ok["started_at"], "2026-08-11 12:31:19")
            self.assertEqual(ok["finished_at"], "2026-08-11 13:32:12")
        finally:
            conn.close()

    def test_limit_is_clamped(self):
        path, _nid = make_env()
        conn = db.connect(path)
        try:
            for i in range(3):
                conn.execute(
                    "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,"
                    "started_at,finished_at,failed_nodes,error,published,detail,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                    (
                        f"r{i}",
                        1,
                        "manual",
                        "scheduler",
                        "completed",
                        "2026-08-11 10:00:00",
                        "2026-08-11 10:01:00",
                        "[]",
                        "",
                        1,
                        "{}",
                    ),
                )
            conn.commit()
            self.assertEqual(len(daily_runs.list_runs(conn, limit=-1)), 1)
            self.assertEqual(len(daily_runs.local_executions(conn, limit=99999)), 3)
        finally:
            conn.close()

    def test_recover_stale_runs(self):
        path, _nid = make_env()
        conn = db.connect(path)
        try:
            for run_id, started in (
                ("stale-1", "2026-08-01 10:00:00"),
                ("fresh-1", _now_local()),
            ):
                conn.execute(
                    "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,"
                    "started_at,finished_at,failed_nodes,error,published,detail,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                    (run_id, 1, "manual", "scheduler", "running", started, "", "[]", "", 0, "{}"),
                )
            conn.commit()
            recovered = daily_runs.recover_stale_runs(conn, stale_hours=6)
            self.assertEqual(recovered, 1)
            stale = conn.execute(
                "SELECT status, error FROM daily_runs WHERE run_id='stale-1'"
            ).fetchone()
            self.assertEqual(stale["status"], "failed")
            self.assertIn("孤儿恢复", stale["error"])
            fresh = conn.execute(
                "SELECT status FROM daily_runs WHERE run_id='fresh-1'"
            ).fetchone()
            self.assertEqual(fresh["status"], "running")
        finally:
            conn.close()

    def test_api_key_missing_marks_error(self):
        path, nid = make_env()
        conn = db.connect(path)
        fake_n8n_db = os.path.join(tempfile.mkdtemp(), "n8n.sqlite")
        n = sqlite3.connect(fake_n8n_db)
        n.execute(
            "CREATE TABLE execution_entity (id INTEGER, workflowId TEXT, mode TEXT, "
            "status TEXT, startedAt TEXT, stoppedAt TEXT, deletedAt TEXT)"
        )
        n.execute(
            "INSERT INTO execution_entity VALUES "
            "(2001,'SkLUnm3uRyBSY84F','manual','failed',"
            "'2026-08-11 04:00:00.000','2026-08-11 04:01:00.000',NULL)"
        )
        n.commit()
        n.close()
        try:
            with mock.patch.object(daily_runs, "N8N_DB", Path(fake_n8n_db)):
                with mock.patch.object(daily_runs.config, "env_value", return_value=""):
                    daily_runs.sync_from_n8n(conn, limit=10)
            row = conn.execute(
                "SELECT error FROM daily_runs WHERE run_id='2001'"
            ).fetchone()
            self.assertIn("API key 缺失", row["error"])
        finally:
            conn.close()

    def test_published_of_time_window(self):
        path, nid = make_env()
        conn = db.connect(path)
        try:
            vid = db.add_volume(conn, nid, 1, "第一卷")
            db.add_chapter(conn, nid, vid, 1, "第一章")
            conn.execute(
                "INSERT INTO publish_logs(chapter_id,platform,action,result,created_at) "
                "VALUES(1,'fanqie','publish','success','2026-08-11 12:40:00'),"
                "(1,'fanqie','publish','success','2026-08-11 14:00:00'),"
                "(1,'fanqie','publish','failed','2026-08-11 12:45:00')"
            )
            conn.commit()
            self.assertEqual(
                daily_runs.published_of(conn, "2026-08-11 12:30:00", "2026-08-11 13:30:00"),
                1,
            )
            self.assertEqual(
                daily_runs.published_of(conn, "2026-08-11 12:30:00", ""),
                2,
            )
        finally:
            conn.close()

    def test_list_and_detail(self):
        path, nid = make_env()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO daily_runs(run_id,novel_id,trigger,status,started_at,"
                "finished_at,failed_nodes,error,published,detail,created_at) "
                "VALUES('77','1','manual','success','2026-08-11 12:00:00',"
                "'2026-08-11 12:10:00','[]','',2,'{}',datetime('now','localtime'))"
            )
            conn.commit()
            runs = daily_runs.list_runs(conn, limit=10)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["run_id"], "77")
            detail = daily_runs.run_detail(conn, "77")
            self.assertEqual(detail["published"], 2)
            self.assertIsNone(daily_runs.run_detail(conn, "999"))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
