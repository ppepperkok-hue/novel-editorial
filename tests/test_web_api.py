import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
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
        self.assertIn("novel-pipeline 实时监控", html)

    def test_chapters_filter_by_novel(self):
        with urlopen(f"{self.base}/api/chapters?novel_id=1", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(data["chapters"]), 1)


if __name__ == "__main__":
    unittest.main()
