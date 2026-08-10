import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import render_workflow


class RenderWorkflowTests(unittest.TestCase):
    def _make_wf(self):
        tmp = Path(tempfile.mkdtemp())
        wf = {
            "name": "test",
            "nodes": [
                {
                    "id": "n-writer",
                    "name": "写手A",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.2,
                    "position": [0, 0],
                    "parameters": {
                        "method": "POST",
                        "url": "https://api.deepseek.com/chat/completions",
                        "authentication": "none",
                        "sendHeaders": True,
                        "headerParameters": {
                            "parameters": [
                                {"name": "Content-Type", "value": "application/json"},
                                {"name": "Authorization", "value": "=Bearer {{ $env.DEEPSEEK_API_KEY }}"},
                            ]
                        },
                        "sendBody": True,
                        "specifyBody": "json",
                        "jsonBody": (
                            "={{ JSON.stringify({model:'deepseek-v4-pro', temperature:0.85, "
                            "messages:[{role:'system',content:'你是写手，写"
                            + render_workflow.TARGET_WORDS_EXPR
                            + "字。'},{role:'user',content:'章纲：'+JSON.stringify($('解析大纲').item.json.chapter1)"
                            + "}]}) }}"
                        ),
                        "options": {},
                    },
                }
            ],
            "connections": {},
        }
        wf_path = tmp / "wf.json"
        wf_path.write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
        return tmp, wf_path

    def test_proxy_render_keeps_target_words_and_task(self):
        tmp, wf_path = self._make_wf()
        with (
            mock.patch.object(render_workflow, "WF", wf_path),
            mock.patch.object(render_workflow, "AGENTS", tmp),
        ):
            (tmp / "writer.md").write_text(
                "---\nmodel: deepseek-v4-pro\ntemperature: 0.85\n---\n\n"
                "你是写手，写{TARGET_WORDS}字。",
                encoding="utf-8",
            )
            render_workflow.main()
        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        node = wf["nodes"][0]
        self.assertIn("/api/agent/run", node["parameters"]["url"])
        body = node["parameters"]["jsonBody"]
        self.assertIn("agent:'写手A'", body)
        self.assertIn(
            "target_words:(($('解析本地资料').first().json.target_words)||2000)",
            body,
        )
        self.assertIn("task:'章纲：'+JSON.stringify", body)
        self.assertNotIn("role:'system'", body)
        params = node["parameters"]
        headers = params.get("headerParameters", {}).get("parameters", [])
        auth = next((h for h in headers if h.get("name") == "Authorization"), None)
        self.assertIsNotNone(auth, "Authorization header should be rendered")
        self.assertIn("$env.PANEL_TOKEN", auth["value"])
        self.assertIn("Bearer", auth["value"])


if __name__ == "__main__":
    unittest.main()
