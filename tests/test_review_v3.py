"""Tests for issues raised in the third-party review report (round 3)."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from novel_pipeline import db  # noqa: E402


def make_db(status="publishing"):
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "t.db")
    conn = db.connect(path)
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,book_id) VALUES('书','都市','设定',?,'b1')",
        (status,),
    )
    conn.execute("INSERT INTO volumes(novel_id,seq,goal) VALUES(1,1,'第一卷')")
    conn.commit()
    conn.close()
    return path


class RecordWorkStateTests(unittest.TestCase):
    def test_finished_status_not_overwritten(self):
        path = make_db(status="finished")
        conn = db.connect(path)
        try:
            from tools import record_work

            record_work.upsert_novel(
                conn,
                {"book_id": "b1", "book_name": "书", "genre": "都市",
                 "premise": "设定", "tags": [], "abstract": "", "protagonists": []},
            )
            row = conn.execute("SELECT status FROM novels WHERE id=1").fetchone()
            self.assertEqual(row["status"], "finished", "record_work must not resurrect a finished book")
        finally:
            conn.close()

    def test_quality_gate_failure_recorded_as_failed_publish(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
                "VALUES(1,1,1,'章纲','draft','第 1 章')"
            )
            conn.commit()
            from tools import record_work

            record_work.upsert_chapters(
                conn,
                1,
                [{"seq": 1, "outline": "章纲", "title": "第 1 章", "status": "draft",
                  "error": "质量门未通过：字数不足", "words": 300, "summary": {}}],
            )
            log = conn.execute(
                "SELECT result, error FROM publish_logs WHERE chapter_id=1 ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(log["result"], "failed")
            self.assertIn("质量门未通过", log["error"])
        finally:
            conn.close()


class MonitorCostAlertTests(unittest.TestCase):
    def test_cost_over_budget_raises_alert(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute("INSERT INTO settings(key,value) VALUES('monthly_budget','1')")
            conn.execute(
                "INSERT INTO cost_logs(novel_id,node_name,model,prompt_tokens,completion_tokens,cost,created_at) "
                "VALUES(1,'x','deepseek-v4-flash',1,1,5,datetime('now','localtime'))"
            )
            conn.commit()
            from novel_pipeline.services import misc

            alerts = misc.load_alerts(conn)
            self.assertTrue(any("成本超限" in i for i in alerts["issues"]))
        finally:
            conn.close()


class AgentsSaveGuardTests(unittest.TestCase):
    def test_absolute_path_rejected(self):
        from novel_pipeline.services import agents

        result = agents.agent_save(
            {"file": r"C:\Windows\win.ini", "model": "x", "temperature": 0.5, "prompt": "足够长的提示词内容用于测试"}
        )
        self.assertFalse(result["ok"])

    def test_traversal_rejected(self):
        from novel_pipeline.services import agents

        result = agents.agent_save(
            {"file": "../escape.md", "model": "x", "temperature": 0.5, "prompt": "足够长的提示词内容用于测试"}
        )
        self.assertFalse(result["ok"])


class ExportPromptProxyTests(unittest.TestCase):
    def test_proxy_mode_short_circuits(self):
        from tools import export_agent_prompts

        with mock.patch("builtins.print") as print_mock:
            export_agent_prompts.main()
        self.assertTrue(
            any("PROXY_MODE" in str(a[0]) for a in print_mock.call_args_list)
        )


class SchedulerBodyTests(unittest.TestCase):
    def test_publishes_chapter_content_not_outline(self):
        path = make_db()
        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO chapters(novel_id,volume_id,seq,outline,status,title) "
                "VALUES(1,1,1,'章纲文本','reviewed','第 1 章')"
            )
            conn.execute(
                "INSERT INTO chapter_content(chapter_id,content,updated_at) "
                "VALUES(1,'正文内容',datetime('now','localtime'))"
            )
            conn.commit()
            from novel_pipeline.publisher import ManualAdapter
            from novel_pipeline.scheduler import Scheduler

            class RecordingAdapter(ManualAdapter):
                def __init__(self):
                    self.sent = []

                def publish(self, chapter_id, text, scheduled_at=None, as_draft=False):
                    self.sent.append(text)
                    return {"result": "ok"}

            adapter = RecordingAdapter()
            Scheduler(adapter=adapter, chapters_per_day=2).tick(conn)
            self.assertEqual(adapter.sent, ["正文内容"])
        finally:
            conn.close()


class MeetingDbIsolationTests(unittest.TestCase):
    def test_run_session_uses_its_own_db(self):
        path = make_db()
        from novel_pipeline.services import meeting_session

        with mock.patch("novel_pipeline.db.connect") as connect_mock:
            with mock.patch.object(meeting_session, "_run_locked"):
                meeting_session.run_session(1, db_path=path)
        self.assertEqual(connect_mock.call_args[0][0], path)


if __name__ == "__main__":
    unittest.main()
