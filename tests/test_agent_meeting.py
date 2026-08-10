import json
import os
import subprocess
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
    conn.execute(
        "INSERT INTO novels(title,genre,premise,status,volume_goal) "
        "VALUES('测试书','都市','测试','publishing','一卷')"
    )
    conn.execute(
        "INSERT INTO chapters(novel_id,seq,outline,status,title,words,score,published_at) "
        "VALUES(1,1,'纲','published','第一章',2000,85,'2026-08-10 10:00:00')"
    )
    conn.execute("INSERT INTO quality_reports(chapter_id,scores,passed) VALUES(1,'{}',1)")
    conn.commit()
    conn.close()
    return path


class DiaryTests(unittest.TestCase):
    def test_daily_diary_writes_for_all_agents(self):
        path = make_db()
        from tools import write_diaries

        payload = {
            "what_done": "写了第一章",
            "observations": [],
            "feelings": "平稳",
            "concerns": [],
            "thoughts": "继续",
        }
        with mock.patch("tools.write_diaries.chat_deepseek") as chat:
            chat.return_value = {
                "text": json.dumps(payload, ensure_ascii=False),
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "model": "deepseek-v4-flash",
            }
            conn = db.connect(path)
            try:
                write_diaries.write(conn, 1, "daily")
                n = conn.execute(
                    "SELECT COUNT(*) c FROM agent_diaries WHERE diary_type='daily'"
                ).fetchone()["c"]
                self.assertEqual(n, 11)
            finally:
                conn.close()

    def test_weekly_diary_writes_mood(self):
        path = make_db()
        from tools import write_diaries

        payload = {
            "week_summary": "本周写了两章",
            "key_events": [],
            "learnings": [],
            "opinions_changed": [],
            "mood_trend": "平稳",
            "next_week_focus": "观察",
            "mood": {"satisfaction": 0.7, "concern": 0.3, "excitement": 0.6, "fatigue": 0.4, "note": ""},
        }
        with mock.patch("tools.write_diaries.chat_deepseek") as chat:
            chat.return_value = {
                "text": json.dumps(payload, ensure_ascii=False),
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                "model": "deepseek-v4-flash",
            }
            conn = db.connect(path)
            try:
                write_diaries.write(conn, 1, "weekly")
                moods = conn.execute("SELECT mood FROM agent_states").fetchall()
                self.assertEqual(len(moods), 11)
                parsed = json.loads(moods[0]["mood"])
                self.assertAlmostEqual(parsed["satisfaction"], 0.7)
            finally:
                conn.close()


class MaterialsTests(unittest.TestCase):
    def test_build_materials_has_briefs(self):
        path = make_db()
        from tools import architect_weekly

        conn = db.connect(path)
        try:
            m = architect_weekly.build_materials(conn, 1)
            self.assertIn("published_chapters", m["context"])
            self.assertEqual(len(m["agent_briefs"]), 11)
            self.assertEqual(m["context"]["quality_summary"]["total"], 1)
        finally:
            conn.close()

    def test_planning_materials_without_novel(self):
        path = make_db()
        from tools import architect_weekly

        conn = db.connect(path)
        try:
            self.assertIsNone(architect_weekly.build_materials(conn, 0))
            m = architect_weekly.build_materials(conn, 0, allow_empty=True)
            self.assertTrue(m["context"]["new_book_planning"])
            self.assertEqual(m["context"]["published_chapters"], 0)
            self.assertEqual(len(m["agent_briefs"]), 11)
        finally:
            conn.close()


class RoundSpeechRetryTests(unittest.TestCase):
    def test_round_speech_retries_and_uses_structured_json(self):
        path = make_db()
        from tools import agent_meeting, architect_weekly

        conn = db.connect(path)
        try:
            materials = architect_weekly.build_materials(conn, 1)
            calls = {"n": 0}

            def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text, max_tokens=1600):
                calls["n"] += 1
                if calls["n"] == 1:
                    text = "好的，我来发言……（散文，不是 JSON）"
                else:
                    text = json.dumps(
                        {
                            "weekly_summary": "本周写了三章",
                            "feelings": "平稳",
                            "opinion": "保持节奏",
                            "concerns": [],
                            "proposals": ["继续推进"],
                            "priority": "中",
                        },
                        ensure_ascii=False,
                    )
                return text, {"prompt_tokens": 1, "completion_tokens": 1}, "mock"

            with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask):
                speech = agent_meeting.round_speech(
                    conn, 1, "planner", materials, [], 1, dry_run=False
                )
            self.assertEqual(calls["n"], 2)
            self.assertEqual(speech["weekly_summary"], "本周写了三章")
        finally:
            conn.close()

    def test_round_speech_keeps_raw_when_all_attempts_fail(self):
        path = make_db()
        from tools import agent_meeting, architect_weekly

        conn = db.connect(path)
        try:
            materials = architect_weekly.build_materials(conn, 1)
            calls = {"n": 0}

            def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text, max_tokens=1600):
                calls["n"] += 1
                return "我不会 JSON，就说散文吧。", {"prompt_tokens": 1, "completion_tokens": 1}, "mock"

            with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask):
                speech = agent_meeting.round_speech(
                    conn, 1, "guard", materials, [], 1, dry_run=False
                )
            self.assertEqual(calls["n"], 2)
            self.assertIn("raw", speech)
            self.assertIn("散文", speech["raw"])
        finally:
            conn.close()


class MeetingDryRunTests(unittest.TestCase):
    def test_meeting_dry_run_full_chain(self):
        path = make_db()
        py = sys.executable
        r = subprocess.run(
            [py, os.path.join(ROOT, "tools", "agent_meeting.py"), "--db", path, "--novel-id", "1", "--dry-run"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            timeout=120,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(out["ok"])
        self.assertIn("eic", out["attendees"])
        self.assertGreaterEqual(out["transcript_len"], 6)

        conn = db.connect(path)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM agent_diaries WHERE diary_type='weekly'").fetchone()[0],
                11,
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM weekly_meetings").fetchone()[0], 1)
        finally:
            conn.close()


class ApplyReportTests(unittest.TestCase):
    def test_apply_report_is_idempotent(self):
        path = make_db()
        from tools import apply_architect

        report = {
            "decisions": {
                "blueprint_updates": [
                    {"seq": 2, "title": "第二章", "outline": "大纲", "hook": "钩子"}
                ],
                "volume_goal_adjust": "下一卷目标",
                "reader_persona": {"age_range": "18-30", "preference": "爽", "avoid": "水"},
            }
        }
        conn = db.connect(path)
        try:
            r1 = apply_architect.apply_report(conn, 1, report)
            r2 = apply_architect.apply_report(conn, 1, report)
            self.assertTrue(r1["ok"])
            self.assertEqual(r1["blueprints"], 1)
            self.assertEqual(r1["blueprints"], r2["blueprints"])
            row = conn.execute("SELECT outline FROM novels WHERE id=1").fetchone()
            outline = json.loads(row["outline"])
            self.assertEqual(len(outline["blueprints"]), 1)
            self.assertEqual(outline["bible"]["reader_persona"]["preference"], "爽")
        finally:
            conn.close()

    def test_apply_report_finish_and_next_book(self):
        path = make_db()
        from tools import apply_architect

        report = {
            "decisions": {
                "blueprint_updates": [],
                "finish_decision": {
                    "should_finish": True,
                    "remaining_chapters": 8,
                    "reasons": ["主线收束"],
                },
            }
        }
        conn = db.connect(path)
        try:
            r = apply_architect.apply_report(conn, 1, report)
            self.assertTrue(r["ok"])
            row = conn.execute(
                "SELECT status, finish_remaining FROM novels WHERE id=1"
            ).fetchone()
            self.assertEqual(row["status"], "finishing")
            self.assertEqual(row["finish_remaining"], 8)

            # finish it, then next book from report
            conn.execute("UPDATE novels SET status='finished' WHERE id=1")
            conn.commit()
            report2 = {
                "decisions": {
                    "next_book": {
                        "book_name": "下一本",
                        "genre": "玄幻",
                        "abstract": "新书简介",
                        "selling_point": "卖点",
                        "protagonist": "主角乙",
                    }
                }
            }
            r2 = apply_architect.apply_report(conn, 1, report2)
            self.assertTrue(r2["next_book_created"])
            nb = conn.execute(
                "SELECT title, genre, status FROM novels WHERE status='planning'"
            ).fetchone()
            self.assertEqual(nb["title"], "下一本")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
