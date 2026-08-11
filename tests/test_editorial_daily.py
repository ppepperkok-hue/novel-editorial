import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from novel_editorial import db
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
        self.novel_id = _seed(self.conn)

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
            "SELECT COUNT(*) c FROM daily_runs WHERE run_id=?",
            (result["run_id"],),
        ).fetchone()
        self.assertEqual(row["c"], 0, "dry-run must not persist fake run records")

    def test_preflight_blocked_records_failed(self):
        self._ok_preflight()
        from tools import editorial_daily as ed

        with mock.patch.object(
            ed.preflight, "check_cookie", return_value=(False, "cookie失效")
        ):
            result = ed.daily(
                self.conn, trigger="manual", dry_run=False, db_path=self.db_path
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
        self.assertEqual(result["run_id"], result["run_id"])

    def _seed_claim(self, task="修完第三章伏笔"):
        self.conn.execute(
            "INSERT INTO agent_actions(agent, task, novel_id, status, claimed_by, priority, created_at) "
            "VALUES('writer', ?, ?, 'claimed', 'writer', 'medium', datetime('now','localtime'))",
            (task, self.novel_id),
        )
        self.conn.commit()

    def _writer_fixture(self):
        meta = {"protagonist": "林舟"}
        outline = {
            "genre": "都市",
            "keywords": "旧书店",
            "bible": {
                "characters": [{"name": "林舟", "role": "主角"}],
                "relationships": [],
                "world_rules": ["旧书店只在夜间开门"],
            },
            "chapter1": {"title": "开篇", "emotion": "好奇", "position": "开篇"},
            "chapter2": {"title": "试探", "emotion": "紧张", "position": "推进"},
        }
        guard = {"constraints": [], "character_beats": {}}
        return meta, outline, guard

    def test_claimed_writer_notes_injected(self):
        self._seed_claim()
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=True)
        ctx.writing_context = "前情提要"
        editorial_daily._load_claimed_writer_notes(ctx, self.conn)
        self.assertIn("你认领的任务", ctx.claimed_notes)
        self.assertIn("修完第三章伏笔", ctx.claimed_notes)
        meta, outline, guard = self._writer_fixture()
        task = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        self.assertIn("你认领的任务", task)
        self.assertIn("今天是兑现日", task)

    def test_no_claims_leave_prompt_unchanged(self):
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=True)
        ctx.writing_context = "前情提要"
        editorial_daily._load_claimed_writer_notes(ctx, self.conn)
        self.assertEqual(ctx.claimed_notes, "")
        meta, outline, guard = self._writer_fixture()
        task = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        self.assertNotIn("你认领的任务", task)

    def test_claim_inject_off_disables_injection(self):
        self._seed_claim()
        with mock.patch("tools.editorial_daily.config.CLAIM_INJECT", False):
            ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=True)
            editorial_daily._load_claimed_writer_notes(ctx, self.conn)
        self.assertEqual(ctx.claimed_notes, "")

    def test_claimed_task_marked_done_when_published(self):
        self._seed_claim()
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=True)
        ctx.published = 2
        editorial_daily._settle_claimed_tasks(ctx, self.conn)
        row = self.conn.execute(
            "SELECT status FROM agent_actions WHERE task='修完第三章伏笔'"
        ).fetchone()
        self.assertEqual(row["status"], "done")

    def test_claimed_task_broken_raises_friction_when_no_publish(self):
        self._seed_claim()
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=True)
        ctx.published = 0
        editorial_daily._settle_claimed_tasks(ctx, self.conn)
        row = self.conn.execute(
            "SELECT status FROM agent_actions WHERE task='修完第三章伏笔'"
        ).fetchone()
        self.assertEqual(row["status"], "claimed")
        rel = self.conn.execute(
            "SELECT friction FROM agent_relations "
            "WHERE agent='writer' AND other='eic' AND novel_id=?",
            (self.novel_id,),
        ).fetchone()
        self.assertIsNotNone(rel)
        self.assertGreater(rel["friction"], 0)

    def test_dispatch_input_includes_claimed_tasks(self):
        self._seed_claim()
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=False)
        captured = {}

        def fake_agent(ctx_arg, node, task, target_words=None):
            captured["task"] = task
            return json.dumps(
                {
                    "chapters": 2,
                    "focus": "f",
                    "assignments": [
                        {"agent": "writer", "task": "写今天两章", "note": ""}
                    ],
                },
                ensure_ascii=False,
            )

        with mock.patch("tools.editorial_daily.config.DISPATCH_MODE", "editorial"):
            with mock.patch("tools.editorial_daily._agent", side_effect=fake_agent):
                editorial_daily._dispatch(
                    ctx, self.conn, {"stock": 0, "target": 2, "need": 2}
                )
        self.assertIn("修完第三章伏笔", captured["task"])

    def test_mood_note_injected_into_writer_task(self):
        self.conn.execute(
            "INSERT INTO agent_states(agent,novel_id,mood,updated_at) "
            "VALUES('writer',?,?,datetime('now','localtime'))",
            (
                self.novel_id,
                json.dumps({"note": "手感正好，想写点狠的", "satisfaction": 0.8}),
            ),
        )
        self.conn.commit()
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=True)
        ctx.writing_context = "前情提要"
        editorial_daily._load_mood(ctx, self.conn, "writer", "mood_notes")
        self.assertIn("手感正好", ctx.mood_notes)
        meta, outline, guard = self._writer_fixture()
        task = editorial_daily._writer_task(ctx, 0, meta, outline, guard, 2000)
        self.assertIn("今日心情", task)

    def test_review_tone_follows_friction(self):
        self.conn.execute(
            "INSERT INTO agent_relations(agent,other,novel_id,familiarity,trust,friction,updated_at) "
            "VALUES('writer','reviewer',?,0,0,0.4,datetime('now','localtime'))",
            (self.novel_id,),
        )
        self.conn.commit()
        tone = editorial_daily._review_tone(
            self.conn, "writer", "reviewer", self.novel_id
        )
        self.assertIn("不留情面", tone)
        tone_low = editorial_daily._review_tone(
            self.conn, "writer", "planner", self.novel_id
        )
        self.assertIn("语气平和", tone_low)

    def test_handle_agency_executes_and_strips(self):
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=False)
        text = json.dumps(
            {
                "passed": True,
                "agency": [
                    {"action": "write_report", "body": "守正检查报告：第三章时间线有歧义"}
                ],
            },
            ensure_ascii=False,
        )
        result = editorial_daily._handle_agency(ctx, "reviewer", text)
        parsed = json.loads(result)
        self.assertTrue(parsed["passed"])
        self.assertNotIn("agency", parsed)
        rows = self.conn.execute(
            "SELECT activity_type FROM agent_activity WHERE agent='reviewer'"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["activity_type"], "agency_report")

    def test_handle_agency_rejects_unknown_action(self):
        ctx = editorial_daily._Ctx(self.novel_id, self.db_path, dry_run=False)
        text = json.dumps(
            {"agency": [{"action": "publish_book", "body": "x"}]}
        )
        editorial_daily._handle_agency(ctx, "写手A", text)
        self.assertTrue(
            any("不在白名单" in w for w in ctx.warnings),
            ctx.warnings,
        )

    def test_meeting_directives_injected(self):
        report = json.dumps(
            {
                "kind": "topic",
                "writing_directives": [
                    "本卷巧思：第 3 章的握手动作在第 20 章回收",
                    "守正确认：主角不知道自己是破绽",
                ],
            },
            ensure_ascii=False,
        )
        self.conn.execute(
            "INSERT INTO weekly_meetings(held_at,novel_id,attendees,topics,report,status,kind) "
            "VALUES(datetime('now','localtime'),?, '[]', '[]', ?, 'completed', 'topic')",
            (self.novel_id, report),
        )
        self.conn.commit()
        directives = editorial_daily._meeting_directives(
            self.conn, self.novel_id
        )
        self.assertEqual(len(directives), 2)
        self.assertIn("握手动作", directives[0])

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
        self.assertEqual(n, 0, "dry-run runs must not touch daily_runs")

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
        rel = self.conn.execute(
            "SELECT friction FROM agent_relations "
            "WHERE agent='reviewer' AND other='writer' AND novel_id=1"
        ).fetchone()
        self.assertIsNotNone(rel, "quality-gate rejection must raise friction")
        self.assertGreater(rel["friction"], 0.0)

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
        guard_audit = self.conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE category='guard' "
            "AND action='guard_check'"
        ).fetchone()["c"]
        self.assertGreaterEqual(guard_audit, 1)
        run_audit = self.conn.execute(
            "SELECT detail FROM audit_logs WHERE category='operation' "
            "AND action='daily_run' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(run_audit)
        run_detail = json.loads(run_audit["detail"])
        self.assertEqual(run_detail["status"], "completed")

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

    def test_failed_agent_usage_is_recorded(self):
        """Cost entries must include failed LLM calls (review P1-2)."""
        ctx = editorial_daily._Ctx(1, self.db_path, dry_run=False)
        with mock.patch(
            "tools.editorial_daily.agent_tool_loop.run",
            return_value={
                "ok": False,
                "error": "boom",
                "model": "deepseek-v4-flash",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        ):
            text = editorial_daily._agent(ctx, "写手A", "任务", target_words=2000)
        self.assertIsNone(text)
        self.assertIn("写手A", ctx.failed_nodes)
        self.assertEqual(len(ctx.costs), 1)
        self.assertEqual(ctx.costs[0]["prompt_tokens"], 7)
        self.assertEqual(ctx.costs[0]["completion_tokens"], 3)

    def test_publish_draft_rejection_is_visible(self):
        """new_article rejection must surface in failed_nodes/error instead of
        silently ending as 'failed with no reason' (review P1-3)."""
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
                return {"code": 1, "message": "草稿创建被拒"}
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
        self.assertEqual(result["status"], "failed")
        self.assertIn("草稿创建被拒", result["error"])
        self.assertIn("发布A", result["failed_nodes"])
        self.assertIn("发布B", result["failed_nodes"])
        row = self.conn.execute(
            "SELECT error FROM daily_runs WHERE run_id=?", (result["run_id"],)
        ).fetchone()
        self.assertIn("草稿创建被拒", row["error"])

    def test_publish_rejection_writes_failed_log(self):
        """publish_article rejection keeps the chapter reviewed and records a
        failed publish_log entry with the platform reason (review P1-3)."""
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
                return {"code": 0, "data": {"item_id": "i1", "volume_id": "v1", "volume_data": [{"volume_id": "v1", "volume_name": "正文"}]}}
            if url.endswith("/publish_article/v0/"):
                return {"code": -2, "message": "章节字数不足"}
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
        self.assertEqual(result["status"], "failed")
        self.assertIn("章节字数不足", result["error"])
        rows = self.conn.execute(
            "SELECT c.seq, c.status FROM chapters c ORDER BY c.seq"
        ).fetchall()
        self.assertTrue(all(r["status"] == "reviewed" for r in rows))
        failed = self.conn.execute(
            "SELECT COUNT(*) c FROM publish_logs WHERE result='failed'"
        ).fetchone()["c"]
        self.assertGreaterEqual(failed, 2)

    def test_compliance_hit_blocks_publish(self):
        """Sensitive-word hits must block the track before publishing."""
        self._ok_preflight()
        bad_text = "他推开门走进院子，风从巷口吹来，远处传来吆喝声。" * 100 + "冰毒"

        def fake_agent(node, task, temperature=None, max_tokens=None, target_words=None, novel_id=None, db_path=None, model=None):
            if node.startswith("写手") or node.startswith("润色"):
                return {"ok": True, "text": bad_text, "model": "mock", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
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
            raise AssertionError("compliance hit must prevent any publish call")

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
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["published"], 0)
        rows = self.conn.execute(
            "SELECT c.seq, c.status FROM chapters c ORDER BY c.seq"
        ).fetchall()
        self.assertTrue(all(r["status"] == "draft" for r in rows))
        failed = self.conn.execute(
            "SELECT COUNT(*) c FROM publish_logs WHERE result='failed' AND "
            "error LIKE '%合规拦截%'"
        ).fetchone()["c"]
        self.assertGreaterEqual(failed, 2)

    def test_dry_run_skips_cookie_probe(self):
        """Dry-run must stay fully offline (review P3-2)."""
        with mock.patch(
            "tools.editorial_daily.preflight.check_cookie",
            side_effect=AssertionError("dry-run must not probe Fanqie"),
        ):
            with mock.patch(
                "tools.editorial_daily.preflight.check_already_ran", return_value=False
            ):
                with mock.patch(
                    "tools.editorial_daily.preflight.check_budget",
                    return_value=(True, 0.0),
                ):
                    with mock.patch(
                        "tools.editorial_daily.preflight.check_active_book",
                        return_value=(True, ""),
                    ):
                        result = editorial_daily.daily(
                            self.conn, trigger="manual", dry_run=True, db_path=self.db_path
                        )
        self.assertEqual(result["status"], "completed", result)


if __name__ == "__main__":
    unittest.main()
