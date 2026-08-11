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
    def test_round_speech_injects_collaboration_context(self):
        path = make_db()
        from tools import agent_meeting, architect_weekly, mailroom

        conn = db.connect(path)
        try:
            mailroom.send(conn, "eic", "planner", "会前先看下市场热点", subject="提醒", novel_id=1)
            materials = architect_weekly.build_materials(conn, 1)
            captured = {}

            def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                         max_tokens=1600, tools=None, messages=None, system_override=None):
                captured["system"] = system_override
                return (
                    json.dumps(
                        {
                            "weekly_summary": "小结",
                            "feelings": "平稳",
                            "opinion": "意见",
                            "concerns": [],
                            "proposals": [],
                            "priority": "中",
                        }
                    ),
                    {"prompt_tokens": 1, "completion_tokens": 1},
                    "mock",
                    [],
                )

            with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask):
                agent_meeting.round_speech(
                    conn, 1, "planner", materials, [], 1, dry_run=False
                )
            system = captured.get("system") or ""
            self.assertIn("编辑部协作上下文", system)
            self.assertIn("来自 eic", system)
            self.assertIn("会前先看下市场热点", system)
        finally:
            conn.close()

    def test_round_speech_retries_and_uses_structured_json(self):
        path = make_db()
        from tools import agent_meeting, architect_weekly

        conn = db.connect(path)
        try:
            materials = architect_weekly.build_materials(conn, 1)
            calls = {"n": 0}

            def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                         max_tokens=1600, tools=None, messages=None, system_override=None):
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
                return text, {"prompt_tokens": 1, "completion_tokens": 1}, "mock", []

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

            def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                         max_tokens=1600, tools=None, messages=None, system_override=None):
                calls["n"] += 1
                return "我不会 JSON，就说散文吧。", {"prompt_tokens": 1, "completion_tokens": 1}, "mock", []

            with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask):
                speech = agent_meeting.round_speech(
                    conn, 1, "guard", materials, [], 1, dry_run=False
                )
            self.assertEqual(calls["n"], 2)
            self.assertIn("raw", speech)
            self.assertIn("散文", speech["raw"])
        finally:
            conn.close()

    def test_round_speech_calls_knowledge_tool_in_meeting(self):
        path = make_db()
        from tools import agent_meeting, architect_weekly

        conn = db.connect(path)
        try:
            materials = architect_weekly.build_materials(conn, 1)
            calls = {"n": 0, "first_tools": None, "first_system": None, "second_messages": None}

            def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                         max_tokens=1600, tools=None, messages=None, system_override=None):
                calls["n"] += 1
                if calls["n"] == 1:
                    calls["first_tools"] = tools
                    calls["first_system"] = system_override
                    tool_call = {
                        "id": "call_9",
                        "type": "function",
                        "function": {
                            "name": "get_knowledge",
                            "arguments": '{"topic": "伏笔"}',
                        },
                    }
                    return "", {"prompt_tokens": 1, "completion_tokens": 1}, "mock", [tool_call]
                calls["second_messages"] = messages
                text = json.dumps(
                    {
                        "speech": "我觉得伏笔回收得按知识库来。",
                        "weekly_summary": "小结",
                        "feelings": "平稳",
                        "opinion": "意见",
                        "concerns": [],
                        "proposals": [],
                        "priority": "中",
                    },
                    ensure_ascii=False,
                )
                return text, {"prompt_tokens": 1, "completion_tokens": 1}, "mock", []

            with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask):
                speech = agent_meeting.round_speech(
                    conn, 1, "planner", materials, [], 1, dry_run=False
                )
            self.assertEqual(calls["n"], 2)
            self.assertEqual(calls["first_tools"][0]["function"]["name"], "get_knowledge")
            self.assertIn("可用工具", calls["first_system"])
            self.assertIn("get_novel_knowledge", calls["first_system"])
            self.assertIn("开篇钩子", calls["first_system"])
            roles = [m["role"] for m in calls["second_messages"]]
            self.assertIn("tool", roles)
            self.assertEqual(speech["speech"], "我觉得伏笔回收得按知识库来。")
        finally:
            conn.close()


class MeetingDryRunTests(unittest.TestCase):
    def test_meeting_dry_run_full_chain(self):
        path = make_db()
        py = sys.executable
        out_dir = tempfile.mkdtemp()
        r = subprocess.run(
            [
                py,
                os.path.join(ROOT, "tools", "agent_meeting.py"),
                "--db", path,
                "--novel-id", "1",
                "--dry-run",
                "--out", out_dir,
            ],
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
            session = conn.execute(
                "SELECT id, status FROM meeting_sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(session["status"], "finished")
            weekly = conn.execute(
                "SELECT session_id FROM weekly_meetings ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertEqual(weekly["session_id"], session["id"])
        finally:
            conn.close()


class ApplyReportTests(unittest.TestCase):
    def _next_book_report(self):
        return {
            "decisions": {
                "next_book": {
                    "book_name": "Test Book",
                    "genre": "玄幻",
                    "abstract": "A premise",
                    "selling_point": "hook",
                    "protagonist": "Lin",
                }
            }
        }

    def test_create_planning_skips_when_another_planning_exists(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            # A different planning novel already awaits confirmation.
            conn.execute(
                "INSERT INTO novels(title,genre,premise,selling_point,platform,status,"
                "abstract,protagonists,updated_at) "
                "VALUES('旧规划','都市','p','','fanqie','planning','a','[]',"
                "datetime('now','localtime'))"
            )
            conn.commit()
            r = apply_architect.create_planning_from_next_book(
                conn, self._next_book_report()
            )
            self.assertTrue(r["ok"])
            self.assertTrue(r.get("skipped"))
            count = conn.execute(
                "SELECT COUNT(*) c FROM novels WHERE status='planning'"
            ).fetchone()["c"]
            self.assertEqual(count, 1, "must not incubate a second planning book")
        finally:
            conn.close()

    def test_create_planning_from_next_book_idempotent(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            report = {
                "decisions": {
                    "next_book": {
                        "book_name": "Test Book",
                        "genre": "玄幻",
                        "abstract": "A premise",
                        "selling_point": "hook",
                        "protagonist": "Lin",
                    }
                },
                "cover_prompt": "cover art prompt",
            }
            r1 = apply_architect.create_planning_from_next_book(conn, report)
            r2 = apply_architect.create_planning_from_next_book(conn, report)
            self.assertTrue(r1["ok"])
            self.assertFalse(r1["duplicate"])
            self.assertTrue(r2["duplicate"])
            self.assertEqual(r1["id"], r2["id"])
            row = conn.execute(
                "SELECT title, genre, status, cover_prompt FROM novels WHERE id=?",
                (r1["id"],),
            ).fetchone()
            self.assertEqual(row["status"], "planning")
            self.assertEqual(row["cover_prompt"], "cover art prompt")
        finally:
            conn.close()

    def test_create_planning_requires_next_book(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            r = apply_architect.create_planning_from_next_book(
                conn, {"decisions": {}}
            )
            self.assertFalse(r["ok"])
        finally:
            conn.close()

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

    def test_apply_report_skips_next_book_when_planning_exists(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            conn.execute("UPDATE novels SET status='finished' WHERE id=1")
            conn.execute(
                "INSERT INTO novels(title,genre,premise,selling_point,platform,status,"
                "abstract,protagonists,updated_at) "
                "VALUES('已有规划','都市','p','','fanqie','planning','a','[]',"
                "datetime('now','localtime'))"
            )
            conn.commit()
            r = apply_architect.apply_report(conn, 1, self._next_book_report())
            self.assertTrue(r["ok"])
            self.assertFalse(r["next_book_created"])
            count = conn.execute(
                "SELECT COUNT(*) c FROM novels WHERE status='planning'"
            ).fetchone()["c"]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_apply_report_persists_character_updates(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            conn.execute(
                "INSERT INTO characters(novel_id,name,role,traits,goals,state,first_seen_chapter) "
                "VALUES(1,'林舟','主角','冷静','变强','{}',1)"
            )
            conn.commit()
            report = {
                "decisions": {
                    "character_updates": [
                        {
                            "name": "林舟",
                            "current_state": "查明真相后心境松动",
                            "change_log": "本周确认主角动机转变",
                            "arc": "觉醒",
                        },
                        {
                            "name": "新角色",
                            "role": "配角",
                            "current_state": "初登场",
                            "change_log": "本周新角色加入主线",
                        },
                    ]
                }
            }
            r = apply_architect.apply_report(conn, 1, report)
            self.assertTrue(r["ok"])
            row = conn.execute(
                "SELECT state FROM characters WHERE novel_id=1 AND name='林舟'"
            ).fetchone()
            state = json.loads(row["state"])
            self.assertEqual(state["current_state"], "查明真相后心境松动")
            self.assertEqual(state["last_weekly_change"], "本周确认主角动机转变")
            evo = conn.execute(
                "SELECT chapter_id, change_log, arc FROM character_evolution "
                "WHERE novel_id=1 AND name='林舟'"
            ).fetchone()
            self.assertEqual(evo["chapter_id"], 0)
            self.assertEqual(evo["change_log"], "本周确认主角动机转变")
            self.assertEqual(evo["arc"], "觉醒")
            new_char = conn.execute(
                "SELECT role FROM characters WHERE novel_id=1 AND name='新角色'"
            ).fetchone()
            self.assertEqual(new_char["role"], "配角")
        finally:
            conn.close()

    def test_character_updates_idempotent(self):
        path = make_db()
        from tools import apply_architect

        conn = db.connect(path)
        try:
            report = {
                "decisions": {
                    "character_updates": [
                        {
                            "name": "林舟",
                            "change_log": "同样的周会结论",
                        }
                    ]
                }
            }
            apply_architect.apply_report(conn, 1, report)
            apply_architect.apply_report(conn, 1, report)
            count = conn.execute(
                "SELECT COUNT(*) c FROM character_evolution "
                "WHERE novel_id=1 AND change_log='同样的周会结论'"
            ).fetchone()["c"]
            self.assertEqual(count, 1, "identical weekly change must not duplicate")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
