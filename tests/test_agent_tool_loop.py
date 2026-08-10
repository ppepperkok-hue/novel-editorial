import json
import unittest
from unittest import mock

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
    def test_no_tool_calls_single_round(self):
        with mock.patch(
            "tools.agent_tool_loop.chat_deepseek",
            return_value=_resp("直接回答"),
        ) as chat:
            r = agent_tool_loop.run("writer", "写一章", target_words=2000)
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

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None):
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
            r = agent_tool_loop.run("writer", "写章末钩子")
        self.assertEqual(calls["n"], 4)
        self.assertEqual(r["text"], "基于知识包的最终回答")
        self.assertEqual(r["attempts"], 2)
        self.assertEqual(r["used_knowledge"][0]["topic"], "钩子")
        self.assertTrue(r["used_knowledge"][0]["files"])

    def test_tools_failure_degrades_to_plain_call(self):
        calls = {"n": 0}

        def fake(model, system, user, temperature=0.5, max_tokens=1600, messages=None, tools=None):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise RuntimeError("tools unsupported")
            return _resp("降级回答")

        with mock.patch("tools.agent_tool_loop.chat_deepseek", side_effect=fake):
            r = agent_tool_loop.run("planner", "做大纲")
        self.assertTrue(r["ok"])
        self.assertEqual(r["text"], "降级回答")
        self.assertTrue(r["degraded"])
        self.assertEqual(calls["n"], 4)

    def test_unknown_agent_raises(self):
        with self.assertRaises(ValueError):
            agent_tool_loop.run("nobody", "x")


if __name__ == "__main__":
    unittest.main()
