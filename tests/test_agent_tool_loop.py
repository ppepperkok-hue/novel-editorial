import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_editorial import db
from novel_editorial.services import knowledge
from tools import agent_tool_loop


def _resp(text, tool_calls=None):
    return {
        "text": text,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "model": "deepseek-v4-flash",
        "tool_calls": tool_calls or [],
    }


def _tool_call(name="get_knowledge", arguments='{"topic": "钩子"}'):
    return {
        "id": "call_1",
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


class AgentToolLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.kdir = Path(self.tmpdir) / "knowledge"
        self.kdir.mkdir(exist_ok=True)
        with open(
            self.kdir / "opening-hooks.md",
            "w",
            encoding="utf-8",
        ) as f:
            f.write(
                "---\n"
                "title: 开篇钩子\n"
                'agents: ["writer", "planner"]\n'
                'keywords: ["钩子", "开篇"]\n'
                "type: craft\n"
                "---\n"
                "开篇钩子：第一章结尾要留悬念，钩子越具体越好。\n"
            )
        self._kp = mock.patch.object(knowledge, "KNOWLEDGE_DIR", self.kdir)
        self._kp.start()
        self.addCleanup(self._kp.stop)

    def test_unwrap_keeps_collaboration_fields(self):
        raw = '{"text": "正文", "outbox": [{"to": "eic", "body": "留言"}]}'
        self.assertEqual(agent_tool_loop._unwrap_text(raw), raw)
        plain = '{"text": "只有正文"}'
        self.assertEqual(agent_tool_loop._unwrap_text(plain), "只有正文")

    def test_no_tool_calls_single_round(self):
        with mock.patch(
            "tools.agent_tool_loop.chat_deepseek",
            return_value=_resp("直接回答"),
        ) as chat:
            r = agent_tool_loop.run("writer", "写一章", target_words=2000, db_path=self.db_path)
        self.assertTrue(r["ok"])
        self.assertEqual(r["text"], "直接回答")
        self.assertEqual(r["attempts"], 1)
        self.assertEqual(r["used_knowledge"], [])
        self.assertFalse(r["degraded"])
        call = chat.call_args
        self.assertEqual(call.kwargs["tools"][0]["function"]["name"], "get_knowledge")
        self.assertEqual(call.kwargs["tools"][1]["function"]["name"], "get_novel_knowledge")
        self.assertIn("可用工具", call.args[1])
        self.assertIn("get_novel_knowledge", call.args[1])

    def test_tool_calls_resolved_and_second_round(self):
        calls = {"n": 0}

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            calls["n"] += 1
            if calls["n"] <= 3:
                return _resp("", [_tool_call()])
            self.assertIsNone(tools)
            self.assertIsNotNone(messages)
            roles = [m["role"] for m in messages]
            self.assertIn("tool", roles)
            tool_msg = next(m for m in messages if m["role"] == "tool")
            self.assertIn("开篇钩子", tool_msg["content"])
            return _resp("基于知识包的最终回答")

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake):
            r = agent_tool_loop.run("writer", "写章末钩子", db_path=self.db_path)
        self.assertEqual(calls["n"], 4)
        self.assertEqual(r["text"], "基于知识包的最终回答")
        self.assertEqual(r["attempts"], 2)
        self.assertEqual(r["used_knowledge"][0]["topic"], "钩子")
        self.assertTrue(r["used_knowledge"][0]["files"])

    def test_tool_use_logs_knowledge_activity(self):
        calls = {"n": 0}

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _resp("", [_tool_call()])
            return _resp("基于知识包的最终回答")

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake):
            r = agent_tool_loop.run("writer", "写章末钩子", db_path=self.db_path)
        self.assertTrue(r["ok"])
        conn = db.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT activity_type, title, detail FROM agent_activity ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        types = [row["activity_type"] for row in rows]
        self.assertIn("knowledge_lookup", types)
        self.assertIn("chapter", types)
        lookup = next(row for row in rows if row["activity_type"] == "knowledge_lookup")
        self.assertIn("钩子", lookup["title"])
        detail = json.loads(lookup["detail"])
        self.assertEqual(detail["tool"], "get_knowledge")
        self.assertGreater(detail["hits"], 0)

    def test_tools_failure_degrades_to_plain_call(self):
        calls = {"n": 0}

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise RuntimeError("tools unsupported")
            return _resp("降级回答")

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake):
            r = agent_tool_loop.run("planner", "做大纲", db_path=self.db_path)
        self.assertTrue(r["ok"])
        self.assertEqual(r["text"], "降级回答")
        self.assertTrue(r["degraded"])
        self.assertEqual(calls["n"], 4)

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            agent_tool_loop.run("nobody", "x", db_path=self.db_path)

    def test_failure_returns_usage_and_model(self):
        """Failed attempts must still surface the accumulated usage so cost
        accounting and the budget fuse stay truthful (review P1-2)."""
        calls = {"n": 0}

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _resp("", [_tool_call()])
            raise RuntimeError("boom")

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake):
            r = agent_tool_loop.run("writer", "x", db_path=self.db_path)
        self.assertFalse(r["ok"])
        self.assertIn("usage", r)
        self.assertIn("model", r)
        self.assertGreaterEqual(r["usage"]["prompt_tokens"], 1)


    def test_activity_traced_after_run(self):
        with mock.patch(
            "tools.agent_tool_loop.chat_deepseek",
            return_value=_resp("reply"),
        ):
            r = agent_tool_loop.run("writer", "task", db_path=self.db_path)
        self.assertTrue(r["ok"])
        conn = db.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT agent, activity_type, title FROM agent_activity"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["agent"], "writer")
        self.assertEqual(rows[0]["activity_type"], "chapter")

    def test_model_override_reaches_llm(self):
        with mock.patch(
            "tools.agent_tool_loop.chat_deepseek",
            return_value=_resp("ok"),
        ) as chat:
            r = agent_tool_loop.run(
                "writer", "task", model="deepseek-v4-pro",
                db_path=self.db_path,
            )
        self.assertTrue(r["ok"])
        self.assertEqual(chat.call_args.args[0], "deepseek-v4-pro")

    def test_empty_final_round_returns_failure_and_traces(self):
        calls = {"n": 0}

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None, json_mode=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return _resp("", [_tool_call()])
            return _resp("")

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake):
            r = agent_tool_loop.run("writer", "task", db_path=self.db_path)
        self.assertFalse(r["ok"])
        self.assertTrue(r["degraded"])
        self.assertIn("final round empty", r["error"])
        conn = db.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT activity_type, title FROM agent_activity"
            ).fetchall()
        finally:
            conn.close()
        types = [row["activity_type"] for row in rows]
        self.assertIn("agent", types)
        self.assertIn("knowledge_lookup", types)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
