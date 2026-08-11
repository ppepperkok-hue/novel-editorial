"""R4-1 tests: editorial workday state machine."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

from novel_editorial import db  # noqa: E402
from tools import workday  # noqa: E402


def _seed(conn, book_id="b1", daily_chapters=2):
    cur = conn.execute(
        "INSERT INTO novels(title,genre,premise,selling_point,platform,status,book_id,"
        "tags,abstract,protagonists,outline,volume_goal,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "旧书店", "都市", "主角经营旧书店", "", "fanqie", "publishing",
            book_id,
            json.dumps(["都市"], ensure_ascii=False),
            "测试书", json.dumps([{"name": "林舟", "role": "主角"}], ensure_ascii=False),
            json.dumps({"bible": {}, "blueprints": []}, ensure_ascii=False),
            "第一卷", "2026-08-11 00:00:00",
        ),
    )
    conn.commit()
    return cur.lastrowid


class WorkdayTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        _seed(self.conn)

    def tearDown(self):
        self.conn.close()
        lock = ROOT / "n8n_tmp" / (Path(self.db_path).stem + ".lock")
        if lock.exists():
            lock.unlink()

    def _ok_preflight(self):
        patcher = mock.patch.multiple(
            "tools.editorial_daily.preflight",
            check_cookie=mock.DEFAULT,
            check_already_ran=mock.DEFAULT,
            check_budget=mock.DEFAULT,
            check_active_book=mock.DEFAULT,
        )
        m = patcher.start()
        m["check_cookie"].return_value = (True, "")
        m["check_already_ran"].return_value = False
        m["check_budget"].return_value = (True, 0.0)
        m["check_active_book"].return_value = (True, "")
        self.addCleanup(patcher.stop)
        return m

    def test_open_write_reaches_awaiting_close(self):
        self._ok_preflight()
        result = workday.open(
            self.conn, trigger="manual", mode="write",
            dry_run=True, db_path=self.db_path,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "awaiting_close")
        self.assertEqual(result["produce"]["status"], "completed")

    def test_open_org_skips_produce(self):
        result = workday.open(
            self.conn, trigger="manual", mode="org",
            dry_run=True, db_path=self.db_path,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["produce"]["status"], "skipped")

    def test_close_org_workday_is_completed_not_failed(self):
        result = workday.open(
            self.conn, trigger="manual", mode="org",
            dry_run=False, db_path=self.db_path,
        )
        closed = workday.close(
            self.conn, result["run_id"], dry_run=True, db_path=self.db_path
        )
        self.assertEqual(closed["status"], "completed", closed)

    def test_open_persists_one_workday_row(self):
        result = workday.open(
            self.conn, trigger="manual", mode="org",
            dry_run=False, db_path=self.db_path,
        )
        self.assertTrue(result["ok"], result)
        rows = self.conn.execute(
            "SELECT phase, status, source, today_plan FROM daily_runs WHERE run_id=?",
            (result["run_id"],),
        ).fetchall()
        self.assertEqual(len(rows), 1, "workday must own exactly one run row")
        self.assertEqual(rows[0]["phase"], "awaiting_close")
        self.assertEqual(rows[0]["source"], "workday")
        plan = json.loads(rows[0]["today_plan"])
        self.assertFalse(plan["produce"])

    def test_close_completed_when_no_pending(self):
        run_id = "workday-test-1"
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,started_at,created_at) "
            "VALUES(?,1,'manual','workday','completed','awaiting_close','write',datetime('now','localtime'),datetime('now','localtime'))",
            (run_id,),
        )
        self.conn.commit()
        result = workday.close(
            self.conn, run_id, dry_run=True, db_path=self.db_path
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        row = self.conn.execute(
            "SELECT phase, status FROM daily_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        self.assertEqual(row["phase"], "finished")

    def test_close_completed_with_pending_actions(self):
        run_id = "workday-test-2"
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,started_at,created_at) "
            "VALUES(?,1,'manual','workday','completed','awaiting_close','write',datetime('now','localtime'),datetime('now','localtime'))",
            (run_id,),
        )
        self.conn.execute(
            "INSERT INTO agent_actions(agent,novel_id,task,status) "
            "VALUES('guard',1,'规则台账模板','pending')"
        )
        self.conn.commit()
        result = workday.close(
            self.conn, run_id, dry_run=True, db_path=self.db_path
        )
        self.assertEqual(result["status"], "completed_with_pending")
        row = self.conn.execute(
            "SELECT status, legacy FROM daily_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        self.assertEqual(row["status"], "completed_with_pending")
        self.assertIn("pending_actions", json.loads(row["legacy"]))

    def test_close_partial_when_published_some(self):
        run_id = "workday-test-3"
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,published,started_at,created_at) "
            "VALUES(?,1,'manual','workday','partial','awaiting_close','write',1,datetime('now','localtime'),datetime('now','localtime'))",
            (run_id,),
        )
        self.conn.commit()
        result = workday.close(
            self.conn, run_id, dry_run=True, db_path=self.db_path
        )
        self.assertEqual(result["status"], "partial")

    def test_resume_returns_to_awaiting_close(self):
        self._ok_preflight()
        run_id = "workday-resume-1"
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,started_at,created_at) "
            "VALUES(?,1,'manual','workday','running','awaiting_close','write',datetime('now','localtime'),datetime('now','localtime'))",
            (run_id,),
        )
        self.conn.commit()
        resumed = workday.resume(
            self.conn, run_id, dry_run=True, db_path=self.db_path
        )
        self.assertTrue(resumed["ok"], resumed)
        self.assertEqual(resumed["status"], "awaiting_close")

    def test_open_blocked_by_existing_lock(self):
        from tools import preflight  # noqa: E402

        lock_path = ROOT / "n8n_tmp" / (Path(self.db_path).stem + ".lock")
        locked, _ = preflight.acquire_lock(lock_path)
        self.assertTrue(locked)
        try:
            result = workday.open(
                self.conn, trigger="manual", mode="org",
                dry_run=True, db_path=self.db_path,
            )
        finally:
            preflight.release_lock(lock_path)
        self.assertFalse(result["ok"])
        self.assertFalse(result.get("locked"))

    def test_open_broadcasts_workday_start(self):
        result = workday.open(
            self.conn, trigger="manual", mode="org",
            dry_run=False, db_path=self.db_path,
        )
        self.assertTrue(result["ok"], result)
        rows = self.conn.execute(
            "SELECT subject, from_agent FROM agent_messages "
            "WHERE subject='开工'"
        ).fetchall()
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["from_agent"], "eic")

    def test_milestone_broadcast_fires_once(self):
        for n in range(1, 101):
            self.conn.execute(
                "INSERT INTO chapters(novel_id,seq,outline,status,title) "
                "VALUES(1,?,?, 'published', ?)",
                (n, "o", f"第 {n} 章"),
            )
        self.conn.commit()
        workday._milestone_broadcast(self.conn, 1)
        first = self.conn.execute(
            "SELECT subject FROM agent_messages WHERE subject='里程碑'"
        ).fetchall()
        self.assertGreaterEqual(len(first), 1)
        workday._milestone_broadcast(self.conn, 1)
        second = self.conn.execute(
            "SELECT subject FROM agent_messages WHERE subject='里程碑'"
        ).fetchall()
        self.assertEqual(len(second), len(first))

    def test_open_rejects_unclosed_workday(self):
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,started_at,created_at) "
            "VALUES('wd-open-1',1,'manual','workday','running','awaiting_close','write',datetime('now','localtime'),datetime('now','localtime'))"
        )
        self.conn.commit()
        result = workday.open(
            self.conn, trigger="manual", mode="org",
            dry_run=True, db_path=self.db_path,
        )
        self.assertFalse(result["ok"])
        self.assertIn("尚未收工", result["error"])

    def test_resume_blocked_by_existing_lock(self):
        from tools import preflight  # noqa: E402

        run_id = "wd-resume-lock"
        self.conn.execute(
            "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,phase,mode,started_at,created_at) "
            "VALUES(?,1,'manual','workday','running','awaiting_close','write',datetime('now','localtime'),datetime('now','localtime'))",
            (run_id,),
        )
        self.conn.commit()
        lock_path = ROOT / "n8n_tmp" / (Path(self.db_path).stem + ".lock")
        locked, _ = preflight.acquire_lock(lock_path)
        self.assertTrue(locked)
        try:
            result = workday.resume(
                self.conn, run_id, dry_run=True, db_path=self.db_path
            )
        finally:
            preflight.release_lock(lock_path)
        self.assertFalse(result["ok"])
        self.assertFalse(result.get("locked"))
