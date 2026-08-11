import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_pipeline import db
from tools import editorial_daily, preflight

ROOT = Path(__file__).resolve().parent.parent


def _seed(conn, book_id="b1", daily_chapters=2):
    cur = conn.execute(
        "INSERT INTO novels(title,genre,premise,selling_point,platform,status,book_id,"
        "tags,abstract,protagonists,outline,volume_goal,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "旧书店",
            "都市",
            "主角经营旧书店",
            "",
            "fanqie",
            "publishing",
            book_id,
            json.dumps(["都市"], ensure_ascii=False),
            "这是一本用于流水线测试的长篇网络小说，主角在都市中经营旧书店。",
            json.dumps([{"name": "林舟", "role": "主角", "traits": "", "goals": ""}], ensure_ascii=False),
            json.dumps({"bible": {}, "blueprints": []}, ensure_ascii=False),
            "第一卷 旧书店",
            "2026-08-11 00:00:00",
        ),
    )
    conn.commit()
    novel_id = cur.lastrowid
    conn.execute(
        "INSERT OR REPLACE INTO settings(key,value) VALUES('daily_chapters',?)",
        (str(daily_chapters),),
    )
    conn.commit()
    return novel_id


class EditorialDailyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "t.db")
        self.conn = db.connect(self.db_path)
        _seed(self.conn)

    def tearDown(self):
        self.conn.close()
        lock = ROOT / "n8n_tmp" / (Path(self.db_path).stem + ".lock")
        if lock.exists():
            lock.unlink()

    def _ok_preflight(self):
        patcher = mock.patch.multiple(
            "tools.editorial_daily.preflight",
            check_cookie=mock.DEFAULT,
            check_already_ran=mock.DEFAULT,
            check_budget=mock.DEFAULT,
            check_active_book=mock.DEFAULT,
        )
        m = patcher.start()
        m["check_cookie"].return_value = (True, "")
        m["check_already_ran"].return_value = False
        m["check_budget"].return_value = (True, 0.0)
        m["check_active_book"].return_value = (True, "")
        self.addCleanup(patcher.stop)
        return m

    def test_dry_run_full_chain_completed(self):
        self._ok_preflight()
        result = editorial_daily.daily(
            self.conn, trigger="manual", dry_run=True, db_path=self.db_path
        )
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(result["published"], 2)
        row = self.conn.execute(
            "SELECT status, source, published, failed_nodes FROM daily_runs "
            "WHERE run_id=?",
            (result["run_id"],),
        ).fetchone()
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["source"], "scheduler")
        self.assertEqual(row["published"], 2)
        self.assertEqual(row["failed_nodes"], "[]")

    def test_preflight_blocked_records_failed(self):
        self._ok_preflight()
        from tools import editorial_daily as ed

        with mock.patch.object(
            ed.preflight, "check_cookie", return_value=(False, "cookie失效")
        ):
            result = ed.daily(
                self.conn, trigger="manual", dry_run=True, db_path=self.db_path
            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("cookie失效", result["error"])
        row = self.conn.execute(
            "SELECT status FROM daily_runs WHERE run_id=?", (result["run_id"],)
        ).fetchone()
        self.assertEqual(row["status"], "failed")

    def test_scheduled_disabled_skips_without_row(self):
        self.conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES('daily_enabled','false')"
        )
        self.conn.commit()
        result = editorial_daily.daily(
            self.conn, trigger="scheduled", dry_run=True, db_path=self.db_path
        )
        self.assertTrue(result["skipped"])
        row = self.conn.execute(
            "SELECT COUNT(*) c FROM daily_runs WHERE run_id=?", (result["run_id"],)
        ).fetchone()
        self.assertEqual(row["c"], 0)

    def test_lock_concurrency_blocks_second_run(self):
        self._ok_preflight()
        lock_path = ROOT / "n8n_tmp" / (Path(self.db_path).stem + ".lock")
        locked, _ = preflight.acquire_lock(lock_path)
        self.assertTrue(locked)
        try:
            result = editorial_daily.daily(
                self.conn, trigger="manual", dry_run=True, db_path=self.db_path
            )
        finally:
            preflight.release_lock(lock_path)
        self.assertEqual(result["status"], "failed")
        self.assertIn("运行锁占用", result["error"])

    def test_two_runs_are_idempotent(self):
        self._ok_preflight()
        r1 = editorial_daily.daily(
            self.conn, trigger="manual", dry_run=True, db_path=self.db_path
        )
        r2 = editorial_daily.daily(
            self.conn, trigger="manual", dry_run=True, db_path=self.db_path
        )
        self.assertNotEqual(r1["run_id"], r2["run_id"])
        n = self.conn.execute("SELECT COUNT(*) c FROM daily_runs").fetchone()["c"]
        self.assertEqual(n, 2)

    def test_track_isolation_quality_gate_failure(self):
        """A-track gate failure short-circuits only that track; B still publishes."""
        self._ok_preflight()
        long_text = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100

        def fake_agent(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            if node.startswith("写手"):
                return {"ok": True, "text": long_text, "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("润色"):
                text = "短" if node == "润色A" else long_text
                return {"ok": True, "text": text, "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("提炼"):
                return {"ok": True, "text": json.dumps({"summary": "s"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("审稿") or node.startswith("读者"):
                return {"ok": True, "text": json.dumps({"passed": True, "score": 9, "hook_rating": 9, "would_read_next": True}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("主编"):
                return {"ok": True, "text": json.dumps({"verdict": "pass"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "Planner出大纲":
                return {"ok": True, "text": json.dumps({"chapter_outlines": [{"title": "第一章", "outline": "o"}, {"title": "第二章", "outline": "o"}], "bible": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "守护细纲":
                return {"ok": True, "text": json.dumps({"passed": True, "constraints": [], "character_beats": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "生成作品资料":
                return {"ok": True, "text": json.dumps({"book_name": "旧书店", "abstract": "x" * 60, "protagonist": {"name": "林舟"}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            return {"ok": True, "text": json.dumps({}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

        calls = {"n": 0}

        def fake_fanqie_post(ctx, url, fields, env):
            if url.endswith("/article/new_article/v0/"):
                calls["n"] += 1
                return {
                    "code": 0,
                    "data": {
                        "item_id": "real-item-" + str(calls["n"]),
                        "volume_id": "v1",
                        "volume_data": [{"volume_id": "v1", "volume_name": "正文"}],
                    },
                }
            return {"code": 0}

        def fake_fanqie_get(ctx, url, params, env):
            if url.endswith("/book/book_list/v0"):
                return {
                    "code": 0,
                    "data": {
                        "book_list": [
                            {
                                "book_id": "b1",
                                "chapter_number": 0,
                                "book_name": "旧书店",
                                "abstract": "x" * 60,
                            }
                        ]
                    },
                }
            return {"code": 0, "data": {"item_list": [{"item_id": "real-item-1", "article_status": 1}]}}

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_agent):
            with mock.patch("tools.editorial_daily._fanqie_post", side_effect=fake_fanqie_post):
                with mock.patch("tools.editorial_daily._fanqie_get", side_effect=fake_fanqie_get):
                    with mock.patch("tools.editorial_daily._wrapup") as wrap:
                        result = editorial_daily.daily(
                            self.conn, trigger="manual", dry_run=False, db_path=self.db_path
                        )
                        wrap.assert_called_once()
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["published"], 1)
        rows = self.conn.execute(
            "SELECT c.seq, c.status, c.title, c.words FROM chapters c ORDER BY c.seq"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        by_seq = {r["seq"]: r for r in rows}
        self.assertEqual(by_seq[1]["status"], "draft")
        self.assertEqual(by_seq[2]["status"], "published")

    def test_real_chain_records_chapters_and_costs(self):
        self._ok_preflight()
        long_text = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100

        def fake_agent(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            if node.startswith("写手") or node.startswith("润色"):
                return {"ok": True, "text": long_text, "model": "deepseek-v4-flash", "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
            if node.startswith("提炼"):
                return {"ok": True, "text": json.dumps({"summary": "测试摘要"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("审稿") or node.startswith("读者"):
                return {"ok": True, "text": json.dumps({"passed": True, "score": 9, "hook_rating": 9, "would_read_next": True}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("主编"):
                return {"ok": True, "text": json.dumps({"verdict": "pass"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "生成作品资料":
                return {"ok": True, "text": json.dumps({"book_name": "旧书店", "abstract": "x" * 60, "protagonist": {"name": "林舟"}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "Planner出大纲":
                return {"ok": True, "text": json.dumps({"chapter_outlines": [{"title": "第一章", "outline": "o"}, {"title": "第二章", "outline": "o"}], "bible": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "守护细纲":
                return {"ok": True, "text": json.dumps({"passed": True, "constraints": [], "character_beats": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            return {"ok": True, "text": "{}", "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

        def fake_fanqie_post(ctx, url, fields, env):
            if url.endswith("/book/book_list/v0"):
                return {"code": 0, "data": {"book_list": [{"book_id": "b1", "chapter_number": 0, "book_name": "旧书店", "abstract": "x" * 60}]}}
            if url.endswith("/article/new_article/v0/"):
                return {"code": 0, "data": {"item_id": "i1", "volume_id": "v1", "volume_data": [{"volume_id": "v1", "volume_name": "正文"}]}}
            if url.endswith("/article/new_article/v0/") is False:
                pass
            return {"code": 0}

        calls = {"n": 0}

        def fake_fanqie_get(ctx, url, params, env):
            if url.endswith("/book/book_list/v0"):
                return {"code": 0, "data": {"book_list": [{"book_id": "b1", "chapter_number": 0, "book_name": "旧书店", "abstract": "x" * 60}]}}
            calls["n"] += 1
            return {"code": 0, "data": {"item_list": [{"item_id": "i" + str(calls["n"]), "article_status": 1}]}}

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_agent):
            with mock.patch("tools.editorial_daily._fanqie_post", side_effect=fake_fanqie_post):
                with mock.patch("tools.editorial_daily._fanqie_get", side_effect=fake_fanqie_get):
                    with mock.patch("tools.editorial_daily._wrapup"):
                        result = editorial_daily.daily(
                            self.conn, trigger="manual", dry_run=False, db_path=self.db_path
                        )
        self.assertEqual(result["status"], "completed", result)
        rows = self.conn.execute(
            "SELECT seq, status, fanqie_item_id FROM chapters ORDER BY seq"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["status"] == "published" for r in rows))
        cost = self.conn.execute(
            "SELECT COUNT(*) c FROM cost_logs WHERE run_id LIKE 'scheduler-%'"
        ).fetchone()["c"]
        self.assertGreater(cost, 0)

    def test_exception_after_publish_keeps_published_count(self):
        """An exception after a track published must not zero the run stats."""
        self._ok_preflight()
        long_text = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100

        def fake_agent(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            if node.startswith("写手") or node.startswith("润色"):
                return {"ok": True, "text": long_text, "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("提炼"):
                return {"ok": True, "text": json.dumps({"summary": "s"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("审稿") or node.startswith("读者"):
                return {"ok": True, "text": json.dumps({"passed": True, "score": 9, "hook_rating": 9, "would_read_next": True}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("主编"):
                return {"ok": True, "text": json.dumps({"verdict": "pass"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "生成作品资料":
                return {"ok": True, "text": json.dumps({"book_name": "旧书店", "abstract": "x" * 60, "protagonist": {"name": "林舟"}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "Planner出大纲":
                return {"ok": True, "text": json.dumps({"chapter_outlines": [{"title": "第一章", "outline": "o"}, {"title": "第二章", "outline": "o"}], "bible": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "守护细纲":
                return {"ok": True, "text": json.dumps({"passed": True, "constraints": [], "character_beats": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            return {"ok": True, "text": "{}", "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

        def fake_fanqie_post(ctx, url, fields, env):
            if url.endswith("/article/new_article/v0/"):
                return {"code": 0, "data": {"item_id": "i", "volume_id": "v1", "volume_data": [{"volume_id": "v1", "volume_name": "正文"}]}}
            return {"code": 0}

        def fake_fanqie_get(ctx, url, params, env):
            if url.endswith("/book/book_list/v0"):
                return {"code": 0, "data": {"book_list": [{"book_id": "b1", "chapter_number": 0, "book_name": "旧书店", "abstract": "x" * 60}]}}
            return {"code": 0, "data": {"item_list": []}}

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_agent):
            with mock.patch("tools.editorial_daily._fanqie_post", side_effect=fake_fanqie_post):
                with mock.patch("tools.editorial_daily._fanqie_get", side_effect=fake_fanqie_get):
                    with mock.patch("tools.editorial_daily._wrapup"):
                        with mock.patch(
                            "tools.editorial_daily.steps.build_payload",
                            side_effect=RuntimeError("boom after publish"),
                        ):
                            result = editorial_daily.daily(
                                self.conn, trigger="manual", dry_run=False, db_path=self.db_path
                            )
        self.assertEqual(result["status"], "failed")
        self.assertIn("boom after publish", result["error"])
        self.assertEqual(result["published"], 2)
        row = self.conn.execute(
            "SELECT published FROM daily_runs WHERE run_id=?", (result["run_id"],)
        ).fetchone()
        self.assertEqual(row["published"], 2)

    def test_pending_publish_is_consumed_after_generate(self):
        """A manual run with a chapter override must not permanently raise the
        daily target (the n8n path left pending_publish set forever)."""
        self._ok_preflight()
        long_text = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100

        def fake_agent(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            if node.startswith("写手") or node.startswith("润色"):
                return {"ok": True, "text": long_text, "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("提炼"):
                return {"ok": True, "text": json.dumps({"summary": "s"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("审稿") or node.startswith("读者"):
                return {"ok": True, "text": json.dumps({"passed": True, "score": 9, "hook_rating": 9, "would_read_next": True}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("主编"):
                return {"ok": True, "text": json.dumps({"verdict": "pass"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "生成作品资料":
                return {"ok": True, "text": json.dumps({"book_name": "旧书店", "abstract": "x" * 60, "protagonist": {"name": "林舟"}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "Planner出大纲":
                return {"ok": True, "text": json.dumps({"chapter_outlines": [{"title": "第一章", "outline": "o"}, {"title": "第二章", "outline": "o"}], "bible": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "守护细纲":
                return {"ok": True, "text": json.dumps({"passed": True, "constraints": [], "character_beats": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            return {"ok": True, "text": "{}", "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

        def fake_fanqie_post(ctx, url, fields, env):
            if url.endswith("/article/new_article/v0/"):
                return {"code": 0, "data": {"item_id": "i", "volume_id": "v1", "volume_data": [{"volume_id": "v1", "volume_name": "正文"}]}}
            return {"code": 0}

        def fake_fanqie_get(ctx, url, params, env):
            if url.endswith("/book/book_list/v0"):
                return {"code": 0, "data": {"book_list": [{"book_id": "b1", "chapter_number": 0, "book_name": "旧书店", "abstract": "x" * 60}]}}
            return {"code": 0, "data": {"item_list": []}}

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_agent):
            with mock.patch("tools.editorial_daily._fanqie_post", side_effect=fake_fanqie_post):
                with mock.patch("tools.editorial_daily._fanqie_get", side_effect=fake_fanqie_get):
                    with mock.patch("tools.editorial_daily._wrapup"):
                        result = editorial_daily.daily(
                            self.conn, trigger="manual", dry_run=False,
                            chapters=3, db_path=self.db_path,
                        )
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["published"], 2)
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key='pending_publish'"
        ).fetchone()
        self.assertEqual(row["value"], "0")

    def test_reviewer_failure_blocks_track_publish(self):
        """If the logic reviewer agent fails, that track must not publish
        (n8n semantics: the quality gate never runs for that track)."""
        self._ok_preflight()
        long_text = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100
        calls = []

        def fake_agent(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            calls.append(node)
            if node == "审稿A":
                return {"ok": False, "error": "reviewer crashed", "degraded": True}
            if node.startswith("写手") or node.startswith("润色"):
                return {"ok": True, "text": long_text, "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("提炼"):
                return {"ok": True, "text": json.dumps({"summary": "s"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("审稿") or node.startswith("读者"):
                return {"ok": True, "text": json.dumps({"passed": True, "score": 9, "hook_rating": 9, "would_read_next": True}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node.startswith("主编"):
                return {"ok": True, "text": json.dumps({"verdict": "pass"}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "生成作品资料":
                return {"ok": True, "text": json.dumps({"book_name": "旧书店", "abstract": "x" * 60, "protagonist": {"name": "林舟"}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "Planner出大纲":
                return {"ok": True, "text": json.dumps({"chapter_outlines": [{"title": "第一章", "outline": "o"}, {"title": "第二章", "outline": "o"}], "bible": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            if node == "守护细纲":
                return {"ok": True, "text": json.dumps({"passed": True, "constraints": [], "character_beats": {}}), "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
            return {"ok": True, "text": "{}", "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

        def fake_fanqie_post(ctx, url, fields, env):
            if url.endswith("/article/new_article/v0/"):
                return {"code": 0, "data": {"item_id": "i", "volume_id": "v1", "volume_data": [{"volume_id": "v1", "volume_name": "正文"}]}}
            return {"code": 0}

        def fake_fanqie_get(ctx, url, params, env):
            if url.endswith("/book/book_list/v0"):
                return {"code": 0, "data": {"book_list": [{"book_id": "b1", "chapter_number": 0, "book_name": "旧书店", "abstract": "x" * 60}]}}
            return {"code": 0, "data": {"item_list": []}}

        with mock.patch("tools.editorial_daily.agent_tool_loop.run", side_effect=fake_agent):
            with mock.patch("tools.editorial_daily._fanqie_post", side_effect=fake_fanqie_post):
                with mock.patch("tools.editorial_daily._fanqie_get", side_effect=fake_fanqie_get):
                    with mock.patch("tools.editorial_daily._wrapup"):
                        result = editorial_daily.daily(
                            self.conn, trigger="manual", dry_run=False, db_path=self.db_path
                        )
        self.assertEqual(result["status"], "partial", result)
        self.assertEqual(result["published"], 1)
        rows = self.conn.execute(
            "SELECT seq, status FROM chapters ORDER BY seq"
        ).fetchall()
        by_seq = {r["seq"]: r for r in rows}
        self.assertEqual(by_seq[1]["status"], "draft")
        failed = self.conn.execute(
            "SELECT error FROM publish_logs WHERE result='failed' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(failed)
        self.assertIn("审稿链路失败", failed["error"])
        self.assertEqual(by_seq[2]["status"], "published")
        # The A track must stop after the failed reviewer: no reader/eic/memory.
        self.assertNotIn("读者审稿A", calls)
        self.assertNotIn("主编终审A", calls)
        self.assertNotIn("提炼剧情A", calls)


if __name__ == "__main__":
    unittest.main()
