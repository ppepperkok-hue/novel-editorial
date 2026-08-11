"""S4 tests: outbox extraction, persistence, injected-read marking."""

import json
import os
import tempfile
import unittest
from unittest import mock

from novel_pipeline import db
from tools import editorial_daily, mailroom


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        self.ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)

    def tearDown(self):
        self.conn.close()

    def test_outbox_persisted_and_stripped(self):
        text = json.dumps(
            {
                "passed": True,
                "outbox": [
                    {"to": "writer", "subject": "打回", "body": "第二章逻辑有漏洞"}
                ],
            },
            ensure_ascii=False,
        )
        result = editorial_daily._handle_outbox(self.ctx, "审稿A", text)
        parsed = json.loads(result)
        self.assertTrue(parsed["passed"])
        self.assertNotIn("outbox", parsed)
        msgs = mailroom.list_messages(self.conn, agent="writer")["messages"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["from_agent"], "reviewer")
        self.assertIn("逻辑有漏洞", msgs[0]["body"])

    def test_outbox_failure_is_explicit_warning(self):
        text = json.dumps({"outbox": [{"to": "", "body": "x"}]})
        result = editorial_daily._handle_outbox(self.ctx, "审稿A", text)
        self.assertEqual(result, "{}")  # outbox stripped, no other fields left
        self.assertTrue(
            any("outbox 审稿A" in w for w in self.ctx.warnings),
            self.ctx.warnings,
        )

    def test_prose_text_untouched(self):
        text = "正文里提到 outbox 这个词也不该被解析"
        self.assertEqual(editorial_daily._handle_outbox(self.ctx, "写手A", text), text)

    def test_mark_injected_read(self):
        mailroom.send(self.conn, "eic", "writer", "今天两章归你", novel_id=1)
        mailroom.send(self.conn, "reviewer", "writer", "注意承接", novel_id=1)
        editorial_daily._mark_injected_read(self.ctx, "写手A")
        count = mailroom.unread_count(self.conn, "writer", novel_id=1)
        self.assertEqual(count["unread"], 0)

    def test_agent_integration_persists_outbox_and_marks_read(self):
        mailroom.send(self.conn, "eic", "writer", "早会消息", novel_id=1)

        def fake_run(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            return {
                "ok": True,
                "text": json.dumps(
                    {
                        "verdict": "pass",
                        "outbox": [{"to": "planner", "subject": "建议", "body": "下一卷节奏放慢"}],
                    }
                ),
                "model": "mock",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_run):
            text = editorial_daily._agent(self.ctx, "主编终审A", "任务")
        parsed = json.loads(text)
        self.assertEqual(parsed["verdict"], "pass")
        self.assertNotIn("outbox", parsed)
        planner_msgs = mailroom.list_messages(self.conn, agent="planner")["messages"]
        self.assertEqual(len(planner_msgs), 1)
        self.assertEqual(planner_msgs[0]["from_agent"], "eic")
        writer_unread = mailroom.unread_count(self.conn, "writer", novel_id=1)
        self.assertEqual(writer_unread["unread"], 0)

    def test_dry_run_skips_outbox_and_read_marking(self):
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=True)
        mailroom.send(self.conn, "eic", "writer", "消息", novel_id=1)

        def fake_run(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            return {
                "ok": True,
                "text": json.dumps({"outbox": [{"to": "planner", "body": "x"}]}),
                "model": "mock",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_run):
            editorial_daily._agent(ctx, "主编终审A", "任务")
        self.assertEqual(mailroom.unread_count(self.conn, "writer", novel_id=1)["unread"], 1)
        self.assertEqual(mailroom.list_messages(self.conn, agent="planner")["messages"], [])


if __name__ == "__main__":
    unittest.main()
