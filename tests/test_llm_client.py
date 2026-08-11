import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from novel_editorial.llm_client import LLMClient, LLMError, MockLLMClient


class FakeHandler(BaseHTTPRequestHandler):
    fail_first = False
    calls = 0

    def do_POST(self):
        type(self).calls += 1
        if self.path != "/chat/completions":
            self.send_error(404)
            return
        if type(self).fail_first and type(self).calls == 1:
            self.send_error(500)
            return
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        payload = {"choices": [{"message": {"content": "你好，样张正文。"}}]}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def start_server():
    server = HTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class LlmClientTests(unittest.TestCase):
    def setUp(self):
        FakeHandler.calls = 0
        FakeHandler.fail_first = False
        self.server = start_server()
        self.port = self.server.server_address[1]
        self.addCleanup(self.server.shutdown)

    def test_chat_returns_content(self):
        client = LLMClient(
            api_key="k",
            base_url=f"http://127.0.0.1:{self.port}",
            models={"writing": "m"},
        )
        self.assertEqual(client.chat("system", "user", tier="writing"), "你好，样张正文。")

    def test_retries_then_succeeds(self):
        FakeHandler.fail_first = True
        client = LLMClient(
            api_key="k",
            base_url=f"http://127.0.0.1:{self.port}",
            models={"writing": "m"},
            max_retries=1,
        )
        self.assertEqual(client.chat("system", "user"), "你好，样张正文。")
        self.assertEqual(FakeHandler.calls, 2)

    def test_unconfigured_raises(self):
        client = LLMClient(api_key="", base_url="")
        self.assertFalse(client.configured)
        with self.assertRaises(LLMError):
            client.chat("s", "u")


class MockClientTests(unittest.TestCase):
    def test_scripted_tier_responses(self):
        client = MockLLMClient(responses={"writing": "正文A"})
        self.assertEqual(client.chat("s", "u", tier="writing"), "正文A")
        self.assertEqual(len(client.calls), 1)

    def test_sequence_responses_are_consumed_in_order(self):
        client = MockLLMClient(responses={"reviewing": ["第一轮", "第二轮"]})
        self.assertEqual(client.chat("s", "u", tier="reviewing"), "第一轮")
        self.assertEqual(client.chat("s", "u", tier="reviewing"), "第二轮")

    def test_callable_responses(self):
        client = MockLLMClient(responses={"writing": lambda tier, s, u: f"tier={tier}"})
        self.assertEqual(client.chat("s", "u", tier="writing"), "tier=writing")


if __name__ == "__main__":
    unittest.main()
