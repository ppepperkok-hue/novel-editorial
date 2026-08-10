import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock
from urllib.error import HTTPError
from urllib.request import urlopen

from novel_pipeline import db
from novel_pipeline.web_api import make_handler


class WebApiTests(unittest.TestCase):
    def setUp(self):
        tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(tmpdir, "test.db")
        conn = db.connect(self.db_path)
        nid = db.add_novel(conn, "测试书", "都市", "简介")
        vid = db.add_volume(conn, nid, 1, "第一卷")
        cid = db.add_chapter(conn, nid, vid, 1, "第1章")
        db.update_chapter_after_review(conn, cid, 1200, 8.5, True)
        db.add_quality_report(conn, cid, {"words": 8}, True)
        db.add_publish_log(conn, cid, "fanqie", "publish", "ok", ai_declared=1)
        conn.close()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.db_path))
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.port}"

    def test_dashboard_payload(self):
        with urlopen(f"{self.base}/api/dashboard", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["summary"]["chapters_total"], 1)
        self.assertEqual(data["summary"]["quality_passed"], 1)
        self.assertEqual(len(data["novels"]), 1)
        self.assertEqual(len(data["chapters"]), 1)
        self.assertEqual(len(data["publish_logs"]), 1)

    def test_index_served(self):
        with urlopen(self.base + "/", timeout=10) as resp:
            html = resp.read().decode("utf-8")
        self.assertTrue(
            "<div id=\"root\">" in html or "novel-pipeline 实时监控" in html,
            "监控页应返回 React 控制台或旧版 HTML",
        )

    def test_chapters_filter_by_novel(self):
        with urlopen(f"{self.base}/api/chapters?novel_id=1", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(data["chapters"]), 1)

    def test_agent_run_endpoint_shape(self):
        from novel_pipeline import db as db_mod

        conn = db_mod.connect(self.db_path)
        conn.execute(
            "INSERT INTO knowledge_drafts(kind,title,content,status,created_at) "
            "VALUES('lesson','t','c','draft',datetime('now','localtime'))"
        )
        conn.commit()
        conn.close()
        with mock.patch("tools.agent_tool_loop.run") as run:
            run.return_value = {
                "ok": True,
                "text": "代理回答",
                "used_knowledge": [{"topic": "钩子", "files": ["opening-hooks.md"]}],
                "model": "deepseek-v4-flash",
                "attempts": 2,
                "degraded": False,
            }
            body = json.dumps(
                {"agent": "writer", "task": "写一章", "max_tokens": 2000}
            ).encode("utf-8")
            req = urlopen(
                f"{self.base}/api/agent/run",
                data=body,
                timeout=10,
            )
            data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(data["choices"][0]["message"]["content"], "代理回答")
        self.assertEqual(data["used_knowledge"][0]["topic"], "钩子")

    def test_knowledge_list_and_draft_reject(self):
        from novel_pipeline import db as db_mod

        conn = db_mod.connect(self.db_path)
        cur = conn.execute(
            "INSERT INTO knowledge_drafts(kind,title,content,status,created_at) "
            "VALUES('lesson','测试经验','内容','draft',datetime('now','localtime'))"
        )
        conn.commit()
        did = cur.lastrowid
        conn.close()

        body = json.dumps({"action": "list"}).encode("utf-8")
        with urlopen(f"{self.base}/api/knowledge", data=body, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(len(data["knowledge"]), 6)

        body = json.dumps({"action": "reject", "id": did}).encode("utf-8")
        with urlopen(
            f"{self.base}/api/knowledge_drafts", data=body, timeout=10
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        conn = db_mod.connect(self.db_path)
        status = conn.execute(
            "SELECT status FROM knowledge_drafts WHERE id=?", (did,)
        ).fetchone()["status"]
        conn.close()
        self.assertEqual(status, "rejected")

    def test_novel_knowledge_list_and_upsert(self):
        body = json.dumps(
            {"action": "upsert", "novel_id": 1, "category": "character",
             "entity": "苏晚晴", "content": "筑基中期"}
        ).encode("utf-8")
        with urlopen(
            f"{self.base}/api/novel_knowledge", data=body, timeout=10
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        with urlopen(f"{self.base}/api/novel_knowledge?novel_id=1", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["entity"], "苏晚晴")

    def test_cross_origin_post_rejected(self):
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{self.base}/api/control",
            data=json.dumps({"action": "run_now", "workflow": "daily"}).encode("utf-8"),
            headers={"Origin": "http://evil.example", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)

    def test_text_plain_post_rejected(self):
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{self.base}/api/control",
            data=b'{"action":"run_now"}',
            headers={"Content-Type": "text/plain"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 403)

    def test_panel_token_required_for_non_browser_post(self):
        with mock.patch("novel_pipeline.web_api._panel_token", return_value="secret"):
            req = __import__("urllib.request", fromlist=["Request"]).Request(
                f"{self.base}/api/control",
                data=json.dumps({"action": "run_now", "workflow": "daily"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as ctx:
                urlopen(req, timeout=10)
            self.assertEqual(ctx.exception.code, 403)
            req = __import__("urllib.request", fromlist=["Request"]).Request(
                f"{self.base}/api/control",
                data=json.dumps({"action": "run_now", "workflow": "daily"}).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
                method="POST",
            )
            with urlopen(req, timeout=10) as resp:
                self.assertEqual(resp.status, 200)

    def test_knowledge_save_rejects_path_traversal(self):
        body = json.dumps(
            {"action": "save", "file": "../escape.md", "meta": {"title": "x"}, "body": "内容"}
        ).encode("utf-8")
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{self.base}/api/knowledge",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=10)
        self.assertEqual(ctx.exception.code, 500)
        from novel_pipeline import config

        self.assertFalse((config.ROOT / "escape.md").exists())


if __name__ == "__main__":
    unittest.main()
