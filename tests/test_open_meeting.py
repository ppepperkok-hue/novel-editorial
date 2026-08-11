"""S13 tests: open-meeting chair direction and speaker resolution."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from novel_pipeline.services import meeting_session
from tools import agent_meeting


class OpenMeetingTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.conn = db.connect(os.path.join(self.tmpdir, "t.db"))
        self.attendees = ["writer", "reviewer", "eic"]

    def tearDown(self):
        self.conn.close()

    def _materials(self):
        return {"context": {}, "agent_briefs": {}}

    def test_rounds_mode_keeps_everyone(self):
        with mock.patch("novel_pipeline.services.meeting_session.config.MEETING_MODE", "rounds"):
            speakers = meeting_session._resolve_speakers(
                self.conn, 1, self._materials(), [], "主题", self.attendees, 3
            )
        self.assertEqual(speakers, self.attendees)

    def test_open_mode_round_one_is_everyone(self):
        with mock.patch("novel_pipeline.services.meeting_session.config.MEETING_MODE", "open"):
            speakers = meeting_session._resolve_speakers(
                self.conn, 1, self._materials(), [], "主题", self.attendees, 1
            )
        self.assertEqual(speakers, self.attendees)

    def test_open_mode_chair_ends_meeting(self):
        with mock.patch("novel_pipeline.services.meeting_session.config.MEETING_MODE", "open"):
            with mock.patch(
                "novel_pipeline.services.meeting_session.agent_meeting.chair_direct",
                return_value={"ok": True, "continue": False, "next_agents": [], "note": "结论已达成"},
            ):
                speakers = meeting_session._resolve_speakers(
                    self.conn, 1, self._materials(), [], "主题", self.attendees, 2
                )
        self.assertEqual(speakers, [])

    def test_open_mode_chair_picks_subset(self):
        with mock.patch("novel_pipeline.services.meeting_session.config.MEETING_MODE", "open"):
            with mock.patch(
                "novel_pipeline.services.meeting_session.agent_meeting.chair_direct",
                return_value={"ok": True, "continue": True, "next_agents": ["writer"], "note": ""},
            ):
                speakers = meeting_session._resolve_speakers(
                    self.conn, 1, self._materials(), [], "主题", self.attendees, 2
                )
        self.assertEqual(speakers, ["writer"])

    def test_open_mode_chair_failure_degrades_to_everyone(self):
        with mock.patch("novel_pipeline.services.meeting_session.config.MEETING_MODE", "open"):
            with mock.patch(
                "novel_pipeline.services.meeting_session.agent_meeting.chair_direct",
                side_effect=RuntimeError("boom"),
            ):
                speakers = meeting_session._resolve_speakers(
                    self.conn, 1, self._materials(), [], "主题", self.attendees, 2
                )
        self.assertEqual(speakers, self.attendees)

    def test_chair_direct_parses_response(self):
        def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                     max_tokens=1600, tools=None, messages=None, system_override=None):
            return (
                json.dumps({"continue": True, "next_agents": ["reviewer"], "note": "让守正补充"}),
                {"prompt_tokens": 1, "completion_tokens": 1},
                "mock",
                [],
            )

        with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask) as ask_mock:
            result = agent_meeting.chair_direct(
                self.conn, 1, self._materials(), [], "主题"
            )
        self.assertTrue(result["ok"])
        self.assertTrue(result["continue"])
        self.assertEqual(result["next_agents"], ["reviewer"])
        self.assertIn("编辑部协作上下文", ask_mock.call_args.kwargs.get("system_override") or "")

    def test_chair_direct_unparseable_degrades(self):
        def fake_ask(conn, novel_id, agent, user, temperature, dry_run, mock_text,
                     max_tokens=1600, tools=None, messages=None, system_override=None):
            return "不是 JSON", {"prompt_tokens": 1, "completion_tokens": 1}, "mock", []

        with mock.patch("tools.agent_meeting.ask", side_effect=fake_ask):
            result = agent_meeting.chair_direct(
                self.conn, 1, self._materials(), [], "主题"
            )
        self.assertFalse(result["ok"])
        self.assertFalse(result["continue"])


if __name__ == "__main__":
    unittest.main()
