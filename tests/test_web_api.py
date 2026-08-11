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
        self.assertIn("executions", data, "dashboard must carry executions fallback")
        self.assertIn("updated_at", data)

    def test_build_snapshot_uses_local_runs_without_n8n(self):
        from novel_pipeline.web_api import _build_snapshot

        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO daily_runs(run_id,novel_id,trigger,source,status,"
                "started_at,finished_at,failed_nodes,error,published,detail,created_at) "
                "VALUES('sched-1',1,'manual','scheduler','completed',"
                "'2026-08-11 10:00:00','2026-08-11 10:01:00','[]','',2,'{}',"
                "'2026-08-11 10:00:00')"
            )
            conn.commit()
            snap = _build_snapshot(conn)
        finally:
            conn.close()
        self.assertNotIn("workflows", snap)
        self.assertIn("executions", snap)
        self.assertEqual(snap["executions"][0]["id"], "sched-1")
        self.assertEqual(snap["executions"][0]["workflow"], "日更")

    def test_bad_query_params_do_not_500(self):
        # Required parameters reject garbage explicitly with 400.
        with self.assertRaises(HTTPError) as ctx:
            urlopen(f"{self.base}/api/chapters?novel_id=abc", timeout=10)
        self.assertEqual(ctx.exception.code, 400)
        # Optional parameters fall back to defaults instead of crashing.
        with urlopen(f"{self.base}/api/daily_runs?limit=abc", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("runs", data)

    def test_editorial_read_endpoints(self):
        from tools import mailroom

        conn = db.connect(self.db_path)
        try:
            mailroom.send(conn, "reviewer", "writer", "第二章逻辑有漏洞", novel_id=1)
        finally:
            conn.close()
        with urlopen(f"{self.base}/api/agents/mailbox?agent=writer", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["messages"]), 1)
        for path in ("relations", "memories", "promises"):
            with urlopen(f"{self.base}/api/agents/{path}?agent=writer", timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"], path)
            self.assertIn("items", data)

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
        self.assertEqual(data["entity"], "苏晚晴")
        self.assertIn("merged_into", data)
        self.assertIn("similar", data)
        # Sentence-style entity normalizes to the same row (version 2).
        body = json.dumps(
            {"action": "upsert", "novel_id": 1, "category": "character",
             "entity": "苏晚晴：主角", "content": "筑基后期"}
        ).encode("utf-8")
        with urlopen(
            f"{self.base}/api/novel_knowledge", data=body, timeout=10
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(data["entity"], "苏晚晴")
        with urlopen(f"{self.base}/api/novel_knowledge?novel_id=1", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["entity"], "苏晚晴")
        self.assertEqual(data["items"][0]["version"], 2)

    def test_novel_knowledge_history_and_graph(self):
        body = json.dumps(
            {"action": "upsert", "novel_id": 1, "category": "character",
             "entity": "林一", "content": "练气一层"}
        ).encode("utf-8")
        with urlopen(f"{self.base}/api/novel_knowledge", data=body, timeout=10) as resp:
            upserted = json.loads(resp.read().decode("utf-8"))
        kid = upserted["id"]
        with urlopen(
            f"{self.base}/api/novel_knowledge/history?knowledge_id={kid}", timeout=10
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("items", data)
        with urlopen(
            f"{self.base}/api/novel_knowledge/graph?novel_id=1", timeout=10
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertEqual(len(data["nodes"]), 1)
        self.assertEqual(data["nodes"][0]["label"], "林一")

    def test_daily_runs_endpoints(self):
        with mock.patch(
            "tools.daily_runs._n8n_executions", return_value=[]
        ):
            with urlopen(f"{self.base}/api/daily_runs", timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        self.assertIn("runs", data)
        with self.assertRaises(HTTPError):
            urlopen(
                f"{self.base}/api/daily_runs/detail?run_id=not-exist", timeout=10
            )

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
        # run_workflow_now must be mocked: an unauthorized call is expected to
        # 403 before reaching it, but the authorized branch would otherwise
        # fire a real n8n webhook from the test suite.
        with (
            mock.patch("novel_pipeline.web_api._panel_token", return_value="secret"),
            mock.patch("novel_pipeline.services.control.run_workflow_now") as run,
        ):
            run.return_value = {"ok": True, "workflow": "daily"}
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
            run.assert_called_once_with("daily")

    def test_knowledge_save_rejects_path_traversal(self):
        # Isolate the global alerts log: the API error branch appends to
        # config.ALERTS_LOG, which must not receive test-suite noise.
        alert_file = os.path.join(tempfile.mkdtemp(), "alerts.log")
        body = json.dumps(
            {"action": "save", "file": "../escape.md", "meta": {"title": "x"}, "body": "内容"}
        ).encode("utf-8")
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            f"{self.base}/api/knowledge",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with mock.patch(
            "novel_pipeline.web_api.config.ALERTS_LOG",
            __import__("pathlib").Path(alert_file),
        ):
            with self.assertRaises(HTTPError) as ctx:
                urlopen(req, timeout=10)
            self.assertEqual(ctx.exception.code, 500)
        from novel_pipeline import config

        self.assertFalse((config.ROOT / "escape.md").exists())

    def test_agent_run_injects_pending_actions_and_model(self):
        from novel_pipeline.services import activity

        conn = db.connect(self.db_path)
        activity.create_action(conn, "writer", "伏笔台账", novel_id=1)
        conn.close()
        with mock.patch("tools.agent_tool_loop.run") as run:
            run.return_value = {
                "ok": True, "text": "done", "used_knowledge": [],
                "model": "deepseek-v4-pro", "attempts": 1,
                "degraded": False,
            }
            body = json.dumps(
                {"agent": "writer", "task": "润色正文", "novel_id": 1,
                 "model": "deepseek-v4-pro"}
            ).encode("utf-8")
            with urlopen(f"{self.base}/api/agent/run", data=body, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        call = run.call_args
        self.assertIn("我的待办行动项", call.args[1])
        self.assertIn("伏笔台账", call.args[1])
        self.assertEqual(call.kwargs["model"], "deepseek-v4-pro")

    def test_activity_and_actions_endpoints(self):
        from novel_pipeline.services import activity

        conn = db.connect(self.db_path)
        activity.log_activity(
            conn, "writer", 1, "meeting_speech", "meeting speech",
            {"speech": "hook fast"},
        )
        r = activity.create_action(
            conn, "guard", "build foreshadow ledger", novel_id=1, session_id=3,
            meeting_id=5, detail={"due": "3 days"},
        )
        conn.close()

        with urlopen(f"{self.base}/api/activity", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        speech_items = [i for i in data["items"] if i["activity_type"] == "meeting_speech"]
        self.assertEqual(len(speech_items), 1)
        self.assertEqual(speech_items[0]["detail"]["speech"], "hook fast")
        self.assertEqual(len(data["days"]), 1)

        with urlopen(f"{self.base}/api/agent_actions?status=pending", timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(data["actions"]), 1)
        self.assertEqual(data["actions"][0]["agent"], "guard")
        self.assertEqual(data["actions"][0]["detail"]["due"], "3 days")

        body = json.dumps(
            {"id": r["id"], "status": "done", "result": "ledger built"}
        ).encode("utf-8")
        req = urlopen(f"{self.base}/api/agent_actions/update", data=body, timeout=10)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        with urlopen(f"{self.base}/api/agent_actions?status=done", timeout=10) as resp:
            done = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(done["actions"][0]["result"], "ledger built")

        body = json.dumps(
            {"agent": "reader", "task": "organize reader feedback", "novel_id": 1}
        ).encode("utf-8")
        req = urlopen(f"{self.base}/api/agent_actions/create", data=body, timeout=10)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        with urlopen(f"{self.base}/api/agent_actions?agent=reader", timeout=10) as resp:
            created = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(created["actions"][0]["task"], "organize reader feedback")

    def test_meeting_cancel_endpoint(self):
        from novel_pipeline.services import meeting_session

        conn = db.connect(self.db_path)
        r = meeting_session.create_session(conn, "cancel me")
        sid = r["session_id"]
        conn.close()
        body = json.dumps({"session_id": sid}).encode("utf-8")
        req = urlopen(f"{self.base}/api/meetings/cancel", data=body, timeout=10)
        data = json.loads(req.read().decode("utf-8"))
        self.assertTrue(data["ok"])
        conn = db.connect(self.db_path)
        row = conn.execute(
            "SELECT status FROM meeting_sessions WHERE id=?", (sid,)
        ).fetchone()
        conn.close()
        self.assertEqual(row["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
